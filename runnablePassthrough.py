from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableParallel, RunnablePassthrough


# Model
model = ChatGroq(
    model="openai/gpt-oss-120b"
)

parser = StrOutputParser()


# Code generation prompt
code_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a code generator"),
    ("human", "{topic}")
])


# Explanation prompt
explain_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant who explains code in simple terms"),
    ("human", "Explain the following code in simple words:\n{code}")
])


# First chain
seq = code_prompt | model | parser


# Parallel chain
seq2 = RunnableParallel(
    {
        "code": RunnablePassthrough(),
        "explanation": explain_prompt | model | parser
    }
)


# Final chain
chain = seq | seq2


# Invoke
result = chain.invoke({
    "topic": "Please write a code of palindrome in Python"
})


# Output
print("Generated Code:")
print(result["code"])

print("\nExplanation:")
print(result["explanation"])