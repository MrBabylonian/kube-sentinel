from typing import Literal

from rich.markdown import Markdown
from rich.panel import Panel
from textual.widgets import Static


class ChatMessage(Static):
    """A single chat message bubble."""

    def __init__(
        self, content: str, *, role: Literal["assistant", "user"]
    ) -> None:
        self.role = role
        self._message_content: str = content  # We are using '_message_content' instead of 'content' to avoid shadowing the class attribute.
        super().__init__()

    def render(self) -> Panel:
        """Render the message as a rich panel."""
        if self.role == "assistant":
            body = (
                Markdown(self._message_content)
                if self._message_content
                else ""
            )
            return Panel(
                body,
                title="Kube-Sentinel",
                title_align="left",
                border_style="green",
            )
        return Panel(
            self._message_content,
            title="You",
            title_align="right",
            border_style="cyan",
        )

    def update_content(self, text: str) -> None:
        """Update message content and re-render"""
        self.content = text
        self.refresh()
