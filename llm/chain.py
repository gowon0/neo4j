from langchain_openai import ChatOpenAI

from llm.prompt import prompt


llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.2
)


llm_chain = prompt | llm


def generate_explanation(analysis_data):

    response = llm_chain.invoke({

        "analysis_data": analysis_data

    })

    return response.content