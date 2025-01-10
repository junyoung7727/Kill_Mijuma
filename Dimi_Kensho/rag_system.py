from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.openai import OpenAI
import json
import os
from dotenv import load_dotenv

load_dotenv()

class RAGSystem:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        
        # GPT-4 설정
        Settings.llm = OpenAI(
            model="gpt-4o-mini",
            temperature=0.1,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # 한국어 임베딩 모델 설정
        Settings.embed_model = HuggingFaceEmbedding(
            model_name="jhgan/ko-sbert-nli"
        )
        
        # 데이터 로드 및 인덱스 생성
        self.load_data_and_create_index()
    
    def load_data_and_create_index(self):
        """데이터 로드 및 인덱스 생성"""
        json_path = os.path.join(self.data_dir, 'structured_kr_data.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 문서 생성
        documents = []
        for section, section_data in data.items():
            for root in section_data.get("roots", []):
                items = section_data["tree"].get(root, [])
                for item in items:
                    if item.get("data"):
                        text = (
                            f"섹션: {section}\n"
                            f"항목: {item['korean_name']}\n"
                            f"설명: {item['description']}\n"
                            f"카테고리: {item['category']}\n"
                            f"값: {item['data']['display_value']}\n"
                            f"컨텍스트: {item['data']['context']}\n"
                            f"단위: {item['data']['unit']}"
                        )
                        documents.append(Document(text=text))
        
        # 인덱스 생성
        self.index = VectorStoreIndex.from_documents(documents)
    
    def query(self, question):
        """질문에 대한 답변 생성"""
        try:
            # 프롬프트 템플릿 설정
            system_prompt = """당신은 재무제표 전문가입니다. 
주어진 정보를 바탕으로 명확하고 정확한 답변을 제공해주세요.
숫자는 정확하게 인용하고, 필요한 경우 추가 설명을 제공하세요.
모든 답변은 한국어로 작성해주세요."""

            query_engine = self.index.as_query_engine(
                response_mode="compact",
                similarity_top_k=3
            )
            
            # 질문에 시스템 프롬프트 추가
            formatted_question = f"{system_prompt}\n\n질문: {question}"
            response = query_engine.query(formatted_question)
            
            if not response.response.strip():
                return "죄송합니다. 해당 질문에 대한 관련 정보를 찾을 수 없습니다."
            
            return response.response
            
        except Exception as e:
            print(f"Error details: {type(e)}")
            return f"죄송합니다. 오류가 발생했습니다: {str(e)}"

def main():
    # 데이터 디렉토리 설정
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    
    # RAG 시스템 초기화
    rag = RAGSystem(data_dir)
    
    # 대화 루프
    print("\nRAG 시스템이 준비되었습니다. 질문을 입력하세요 (종료하려면 'q' 입력):")
    while True:
        question = input("\n질문: ")
        if question.lower() == 'q':
            break
        
        answer = rag.query(question)
        print("\n답변:", answer)

if __name__ == "__main__":
    main() 