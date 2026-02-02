import os

from dotenv import load_dotenv
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

load_dotenv(verbose=True)

GOOGLE_VERTEX_API_KEY = os.getenv("GOOGLE_VERTEX_API_KEY")
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")

if not GOOGLE_VERTEX_API_KEY or not GOOGLE_CLOUD_PROJECT:
    raise ValueError(
        "GOOGLE VERTEX API KEY and GOOGLE CLOUD PROJECT must be set in environment variables."
    )


# 1. Define the desired JSON structure using Pydantic
class AgentResponse(BaseModel):
    status: str = Field(
        description="The status of the request, e.g., 'success' or 'error'"
    )
    answer: str = Field(description="The actual response to the user query")
    confidence_score: float = Field(
        description="A value between 0 and 1 representing the confidence"
    )


# 2. Initialize the parser with the Pydantic model
parser = JsonOutputParser(pydantic_object=AgentResponse)

llm = ChatGoogleGenerativeAI(
    model="gemini-3-flash-preview",
    api_key=GOOGLE_VERTEX_API_KEY,
    project=GOOGLE_CLOUD_PROJECT,
    vertexai=True,
    temperature=0,
)

# 3. Create a prompt that includes format_instructions
prompt = ChatPromptTemplate.from_template(
    "You are a helpful assistant. Please answer the user query.\n{format_instructions}\n{query}"
)

# 4. Use partial to inject the format instructions into the prompt
prompt = prompt.partial(format_instructions=parser.get_format_instructions())

# 5. Create the chain using LCEL
structured_chain = prompt | llm | parser

response = structured_chain.invoke(
    {"query": "What is the weather like in Rome? "}
)

print(response)
