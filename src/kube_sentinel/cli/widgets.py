from typing import Literal
from rich.markdown import Markdown
from rich.panel import Panel
from textual.widgets import Static

class ChatMessage(Static)
    """A single chat message bubble."""

    def __init__(
        self, content:str, *, role: Literal["assistant", "user"]
        ) -> None:
        self.role = role
        self.content = content
        super().__init__()

    def render(self) -> Panel:
        """Render the message as a rich panel."""
        if self.role == "assistant":
            body = Markdown(self.content) if self.content else ""
            return Panel(
                body, 
                title="Kube-Sentinel", 
                title_align="left", 
                border_style="green")
        return Panel(
    self.content, 
                title="You", 
                title_align="right", 
                border_style="cyan")

    def update_content(self, text:str) -> None:
        """Update message content and re-render"""
        self.content = text
        self.refresh()

    

