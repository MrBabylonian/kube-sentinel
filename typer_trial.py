import typer
from rich import print
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

app = typer.Typer()

console = Console()

for_markdown = """```javascript
function return_name():
    return "John Doe"
```
"""

print(Markdown(for_markdown))