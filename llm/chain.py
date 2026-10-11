import config.settings  # noqa: F401  (.env 로드)

from langchain_openai import ChatOpenAI

from llm.prompt import prompt, short_prompt


llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.2
)


llm_chain = prompt | llm


# 대시보드용: 짧은 응답, 짧은 타임아웃
short_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.2,
    max_tokens=300,
    timeout=25,
    max_retries=1
)

short_chain = short_prompt | short_llm


def generate_explanation(analysis_data):

    response = llm_chain.invoke({

        "analysis_data": analysis_data

    })

    return response.content


def generate_short_explanation(analysis_data):

    response = short_chain.invoke({

        "analysis_data": analysis_data

    })

    return response.content
