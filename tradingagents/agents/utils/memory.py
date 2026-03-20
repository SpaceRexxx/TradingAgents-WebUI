import os
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import openai

CHROMA_SETTINGS = Settings(allow_reset=True, anonymized_telemetry=False)

class FinancialSituationMemory:
    def __init__(self, name: str, config: dict):
        print(f"--- [DEBUG] In memory.py: Initializing '{name}'. Provider='{config.get('llm_provider')}', URL='{config.get('backend_url')}' ---")

        self.config = config
        embedding_function = None
        backend_url = self.config.get("backend_url", "")

        # --- 重构后的判断逻辑 ---
        
        # Case 1: Google
        if "googleapis.com" in backend_url:
            print("--- [DEBUG] Memory: Matched Google logic. ---")
            google_api_key = os.environ.get("GOOGLE_API_KEY")
            if not google_api_key:
                raise ValueError("GOOGLE_API_KEY environment variable not set for Google provider.")
            embedding_function = embedding_functions.GoogleGenerativeAiEmbeddingFunction(
                api_key=google_api_key, 
                model_name="models/embedding-001"
            )

        # Case 2: Ollama (local)
        elif "localhost:11434" in backend_url:
            print("--- [DEBUG] Memory: Matched Ollama logic. ---")
            embedding_function = embedding_functions.OllamaEmbeddingFunction(
                url="http://localhost:11434/api/embeddings",
                model_name="nomic-embed-text"
            )
        
        # Case 3 (Default): Handles all other OpenAI-compatible APIs (OpenAI, DeepSeek, Groq, etc.)
        else:
            print(f"--- [DEBUG] Memory: Matched OpenAI-compatible logic for URL: {backend_url} ---")
            
            api_key_to_use = None
            model_name_to_use = "text-embedding-3-small" # Default model

            if "deepseek.com" in backend_url:
                print("--- [DEBUG] Memory: Specifically identified DeepSeek. ---")
                api_key_to_use = os.environ.get("DEEPSEEK_API_KEY")
                model_name_to_use = "deepseek-text-embedding-v2"
                if not api_key_to_use:
                    raise ValueError("DEEPSEEK_API_KEY environment variable not set.")
            else: # Default to OpenAI key for others
                api_key_to_use = os.environ.get("OPENAI_API_KEY")

            print(f"--- [DEBUG] Memory: Using API Key starting with '{str(api_key_to_use)[:6]}', Model='{model_name_to_use}', URL='{backend_url}' ---")

            original_base_url = openai.base_url
            original_api_key = openai.api_key
            try:
                openai.base_url = backend_url
                openai.api_key = api_key_to_use
                
                embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                    api_key=api_key_to_use, 
                    model_name=model_name_to_use
                )
            finally:
                openai.base_url = original_base_url
                openai.api_key = original_api_key
        
        # --- 逻辑结束 ---

        if embedding_function is None:
            raise ValueError("Could not create an embedding function for the given configuration.")

        self.chroma_client = chromadb.Client(CHROMA_SETTINGS)
        self.situation_collection = self.chroma_client.get_or_create_collection(
            name=name,
            embedding_function=embedding_function
        )

    def add_situations(self, situations_and_advice: list[tuple[str, str]]):
        # ... (此函数无需修改)
        pass

    def get_memories(self, current_situation: str, n_matches: int = 1) -> list[dict]:
        # ... (此函数无需修改)
        pass

if __name__ == "__main__":
    pass
