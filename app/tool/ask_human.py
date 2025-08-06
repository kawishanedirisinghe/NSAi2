import asyncio
import threading
from typing import Dict, Optional, Tuple
from pydantic import Field
from app.tool.base import BaseTool
from app.logger import logger
import uuid  # Importing the uuid module

class AskHuman(BaseTool):
    """A tool for asking human users questions and getting responses through the web interface."""

    name: str = "ask_human"
    description: str = "Ask a human user a question and wait for their response through the web interface."
    parameters: dict = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to ask the human user.",
            },
        },
        "required": ["question"],
    }

    # Use a dictionary to store pending questions and their corresponding events
    pending_questions: Dict[str, Tuple[str, threading.Event]] = Field(default_factory=dict)
    responses: Dict[str, str] = Field(default_factory=dict)

    # Lock for thread-safe access to shared resources
    lock: threading.Lock = Field(default_factory=threading.Lock)

    def execute(self, question: str, **kwargs) -> Dict:
        """
        Ask a human user a question and wait for a response.
        This method is now synchronous and will block until a response is received or timeout occurs.
        """
        question_id = str(uuid.uuid4())
        response_received_event = threading.Event()

        with self.lock:  # Change made here
            self.pending_questions[question_id] = (question, response_received_event)

        try:
            # Log the question for the web interface to pick up
            logger.info(f"🤔 **AI is asking you a question:**\n\n{question}\n\n*Please type your response below and press send.*")

            # Wait for the response event to be set
            max_wait_time = 300  # 5 minutes
            if not response_received_event.wait(timeout=max_wait_time):
                # Timeout occurred
                logger.warning(f"Timeout waiting for response to question ID: {question_id}")
                return {
                    "observation": "No response received within the timeout period.",
                    "success": False,
                }

            # Response has been received
            with self.lock:  # Change made here
                response = self.responses.pop(question_id)

            logger.info(f"✅ **Received your response:** {response}")
            return {
                "observation": response,
                "success": True,
            }

        except Exception as e:
            logger.error(f"Error in ask_human: {e}")
            return {
                "observation": f"Error asking question: {str(e)}",
                "success": False,
            }
        finally:
            # Clean up the pending question
            with self.lock:  # Change made here
                self.pending_questions.pop(question_id, None)

    def submit_response(self, question_id: str, response: str):
        """
        Submit a response to a pending question.
        This method is called from the web interface thread.
        """
        with self.lock:  # Change made here
            if question_id in self.pending_questions:
                self.responses[question_id] = response
                # Signal that the response has been received
                _, event = self.pending_questions[question_id]
                event.set()
                logger.info(f"Response submitted for question ID: {question_id}")
                return True
            else:
                logger.warning(f"Received response for an unknown or expired question ID: {question_id}")
                return False

    def get_pending_question(self) -> Optional[Tuple[str, str]]:
        """
        Get the latest pending question for the UI.
        Returns a tuple of (question_id, question_text) or None.
        """
        with self.lock:  # Change made here
            if self.pending_questions:
                # Return the most recently added question
                latest_question_id = next(reversed(self.pending_questions))
                question_text, _ = self.pending_questions[latest_question_id]
                return latest_question_id, question_text
        return None