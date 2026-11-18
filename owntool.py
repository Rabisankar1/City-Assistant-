from langchain.tools import tool



@tool #Decorator for creating tools
def get_greeting(name : str) -> str:   #Type hints
    """Generate a Greeting Message for the user."""  #Docstring for the tool
    return f"Hello {name}, welcome to the AI Era Ready for the cook!"

result = get_greeting.invoke({"name" : "Rabisankar"})  #Invoking the tool with input parameters
print(result)  

print(get_greeting.name)
print(get_greeting.description)
print(get_greeting.args) 