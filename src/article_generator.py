import sys
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from log import get_logger
from config import LLM_CONFIG, OPENAI_API_KEY
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = get_logger(__name__)

def get_llm():
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY is not set in the environment variables.")
        raise ValueError("Please set OPENAI_API_KEY in your .env file")
        
    return ChatOpenAI(
        model=LLM_CONFIG.get("model_name", "gpt-4o-mini"),
        temperature=LLM_CONFIG.get("temperature", 0.7),
        openai_api_key=OPENAI_API_KEY
    )

async def generate_article_from_json(ai_analysis: dict, output_path: str):
    """
    Generates a blog article using an LLM based on the ai_analysis dict,
    and saves it to output_path.
    """
    logger.info("Generating article using AI...")
    llm = get_llm()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert blog writer and journalist. Your task is to write an engaging, well-structured article based on a video's AI analysis context. Use Markdown formatting."),
        ("user", "Here is the AI analysis of a video (in JSON format):\n\n{context}\n\nPlease write a captivating article about this video. Create an engaging H1 title, provide an in-depth summary based on the context, and highlight the key takeaways (referencing the reels if any). Make it read like a professional blog post.")
    ])
    
    chain = prompt | llm | StrOutputParser()
    
    try:
        context_str = json.dumps(ai_analysis, indent=2)
        article_content = await chain.ainvoke({"context": context_str})
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(article_content)
            
        logger.info(f"AI-generated article successfully saved to: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error generating article: {e}")
        raise
