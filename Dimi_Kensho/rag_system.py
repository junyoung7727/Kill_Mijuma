from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.openai import OpenAI
import json
import os
from dotenv import load_dotenv

load_dotenv()

def rag():
    # JSON 파일 읽기
    with open('Dimi_Kensho/data/structured_kr_data.json', 'r', encoding='utf-8') as f:
        kr_data = json.load(f)
    
    # JSON 데이터를 문서로 변환
    documents = []
    for section_name, section_data in kr_data.items():
        # 섹션별 문서 생성
        section_text = f"섹션: {section_name}\n"
        
        for group_name, items in section_data.items():
            for item in items:
                # 번역 정보 추가
                translation = item.get('translation', {})
                section_text += f"항목: {translation.get('korean_name', '')}\n"
                section_text += f"설명: {translation.get('description', '')}\n"
                section_text += f"카테고리: {translation.get('category', '')}\n"
                
                # 데이터 값 추가
                if item.get('data'):
                    for data in item['data']:
                        section_text += f"값: {data.get('display_value', '')} {data.get('unit', '')}\n"
                        section_text += f"컨텍스트: {data.get('context', '')}\n"
                
                section_text += "\n"
        
        documents.append(Document(text=section_text))
    
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
    
    # 인덱스 생성
    index = VectorStoreIndex.from_documents(documents)
    
    # 쿼리 엔진 생성
    query_engine = index.as_query_engine(
        response_mode="compact",
        similarity_top_k=3
    )
    

    
    print("\nRAG 시스템 시작")
    q = 0
    while q == 0:
        question = input("질문을 입력하세요: ")
        if question == "q":
            q = 1
            break
        response = query_engine.query(question)
        print(f"답변: {response.response}")

if __name__ == "__main__":
    rag()
