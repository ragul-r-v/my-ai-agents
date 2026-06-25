import asyncio
import json
from datetime import UTC
from pathlib import Path

from google.adk.runners import InMemoryRunner
from google.genai import types

from expense_agent.agent import app


async def generate_traces():
    dataset_path = Path("tests/eval/datasets/basic-dataset.json")
    output_path = Path("artifacts/traces/generated_traces.json")

    print(f"Loading dataset from {dataset_path}...", flush=True)
    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    eval_cases = data.get("eval_cases", [])
    print(f"Loaded {len(eval_cases)} evaluation case(s).", flush=True)

    runner = InMemoryRunner(app=app)
    generated_cases = []

    for i, case in enumerate(eval_cases):
        case_id = case.get("eval_case_id", f"case_{i}")
        prompt_content = case.get("prompt", {})
        prompt_text = prompt_content.get("parts", [{}])[0].get("text", "")

        print(f"\n[{i + 1}/{len(eval_cases)}] Running case: {case_id}", flush=True)
        print(f"Prompt: {prompt_text}", flush=True)

        # Create a fresh session
        session = await runner.session_service.create_session(
            app_name="app", user_id="eval-user"
        )

        message = types.Content(
            role="user", parts=[types.Part.from_text(text=prompt_text)]
        )

        events = []
        async for event in runner.run_async(
            user_id="eval-user",
            session_id=session.id,
            new_message=message,
        ):
            events.append(event)

        # Check if the execution was interrupted / paused for human approval
        hitl_pause = False
        for e in events:
            if e.content and e.content.parts:
                for p in e.content.parts:
                    if p.function_call and p.function_call.name == "adk_request_input":
                        hitl_pause = True
                        break

        if hitl_pause:
            print(
                "  HITL Pause detected. Loading session state to make automated decision...",
                flush=True,
            )
            session_obj = await runner.session_service.get_session(
                app_name="app", user_id="eval-user", session_id=session.id
            )
            is_injection = session_obj.state.get("security_alert", False)
            decision = "reject" if is_injection else "approve"
            print(
                f"  Automated Decision: {decision} (security_alert={is_injection})",
                flush=True,
            )

            # Resume session
            message_resume = types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id="approve",
                            name="adk_request_input",
                            response={"decision": decision},
                        )
                    )
                ],
            )

            async for event in runner.run_async(
                user_id="eval-user",
                session_id=session.id,
                new_message=message_resume,
            ):
                events.append(event)

        # Format events to dictionary format compatible with AgentEvent schema
        formatted_events = []
        # First event is the user prompt
        formatted_events.append(
            {
                "author": "user",
                "content": {"role": "user", "parts": [{"text": prompt_text}]},
            }
        )

        # Append all events from the run with strictly allowed fields
        from datetime import datetime

        for e in events:
            formatted_event = {"author": e.author or "expense_processor"}
            if e.content:
                formatted_event["content"] = e.content.model_dump(
                    mode="json", exclude_none=True
                )
            if e.timestamp:
                formatted_event["event_time"] = datetime.fromtimestamp(
                    e.timestamp, tz=UTC
                ).isoformat()
            if e.actions and e.actions.state_delta is not None:
                formatted_event["state_delta"] = e.actions.state_delta
            # active_tools can be omitted or empty

            formatted_events.append(formatted_event)

        # Extract the final output message
        final_text = None
        if events:
            # Find the last event that had output
            last_output_event = None
            for e in reversed(events):
                if e.output:
                    last_output_event = e
                    break

            if last_output_event and last_output_event.output:
                output_data = last_output_event.output
                if isinstance(output_data, dict):
                    if "message" in output_data:
                        final_text = output_data["message"]
                    elif "status" in output_data:
                        status = output_data["status"]
                        amount = output_data.get("amount", 0.0)
                        submitter = output_data.get("submitter", "unknown")
                        final_text = f"Expense {status}: ${amount:.2f} from {submitter}"
                else:
                    final_text = str(output_data)

        if not final_text:
            final_text = "No final message from workflow."

        print(f"  Final Response: {final_text}", flush=True)

        responses = [{"response": {"role": "model", "parts": [{"text": final_text}]}}]

        # Build evaluation case format
        generated_cases.append(
            {
                "eval_case_id": case_id,
                "prompt": prompt_content,
                "agent_data": {
                    "agents": {"expense_processor": {}},
                    "turns": [
                        {
                            "turn_index": 0,
                            "turn_id": "turn_0",
                            "events": formatted_events,
                        }
                    ],
                },
                "responses": responses,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"eval_cases": generated_cases}, f, indent=2)

    print(f"\nSuccessfully wrote generated traces to {output_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(generate_traces())
