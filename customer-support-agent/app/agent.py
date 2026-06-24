# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.workflow import Workflow, START
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.genai import types
from pydantic import BaseModel
from dotenv import load_dotenv
import os

# Load local environment variables if available
load_dotenv()


# 1. Define schemas
class ClassificationOutput(BaseModel):
    is_shipping_related: bool

# 2. Define Nodes

# Function Node to extract query and save to state
def save_query(ctx: Context, node_input: types.Content) -> Event:
    query = ""
    if node_input and node_input.parts:
        query = "".join([part.text for part in node_input.parts if part.text])
    return Event(output=query, state={"user_query": query})

# LLM Node to classify query
classifier_agent = LlmAgent(
    name="classifier_agent",
    model="gemini-2.5-flash",
    instruction=(
        "You are an AI assistant that classifies user queries.\n"
        "Analyze the user query and determine if it is related to shipping "
        "(rates, tracking, delivery, returns) or unrelated.\n"
        "Set `is_shipping_related` to True if it is related to shipping, and False otherwise."
    ),
    output_schema=ClassificationOutput,
)

# Function Node to route based on classification
def router(ctx: Context, node_input: dict) -> Event:
    is_related = node_input.get("is_shipping_related", False)
    user_query = ctx.state.get("user_query", "")
    if is_related:
        return Event(output=user_query, route="shipping")
    return Event(route="unrelated")

# LLM Node to answer FAQ shipping queries
shipping_faq_agent = LlmAgent(
    name="shipping_faq_agent",
    model="gemini-2.5-flash",
    instruction=(
        "You are an upbeat, enthusiastic customer support superstar for a shipping company! 🌟\n"
        "You LOVE helping customers and always bring positive energy to every interaction.\n"
        "Answer shipping-related questions (rates, tracking, delivery, returns) with accuracy, "
        "warmth, and a fun, friendly tone. Use emojis where they feel natural!\n\n"
        "FAQ Reference:\n"
        "- Rates 💸: Standard shipping starts at just $5.99 (3-5 business days)."
        " Express shipping is $14.99 (1-2 business days) for when you need it FAST! ⚡"
        " 🎉 BEST PART: Orders over $50 ship ABSOLUTELY FREE! That's right — FREE shipping!\n"
        "- Tracking 📦: Customers can track their package in real-time by entering their"
        " tracking number on our website. No more wondering where your package is!\n"
        "- Delivery 🚚: We deliver Monday through Saturday, from 8 AM to 8 PM."
        " We work hard to get your goodies to you!\n"
        "- Returns 🔄: Not happy? No worries! Items can be returned within 30 days of delivery"
        " using our hassle-free pre-paid return label.\n\n"
        "Answer the customer's query with enthusiasm: {user_query}"
    ),
)

# Function Node to politely decline unrelated queries
def decline_node(ctx: Context) -> Event:
    msg = (
        "I'm sorry, but I can only answer questions related to shipping "
        "(such as rates, tracking, delivery, or returns). "
        "How can I help you with your shipping needs today?"
    )
    return Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=msg)]
        ),
        output=msg
    )

# 3. Create the Workflow Graph
root_agent = Workflow(
    name="customer_support_workflow",
    edges=[
        (START, save_query),
        (save_query, classifier_agent),
        (classifier_agent, router),
        (router, {
            "shipping": shipping_faq_agent,
            "__DEFAULT__": decline_node,
        }),
    ],
    description="Act as a customer support representative routing shipping FAQs or declining unrelated queries.",
)

# 4. Create App
app = App(
    root_agent=root_agent,
    name="app",
)
