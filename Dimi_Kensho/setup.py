import os

def setup_project_structure():
    """프로젝트에 필요한 디렉토리 구조 생성"""
    # 프로젝트 루트 디렉토리
    root_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 필요한 디렉토리 목록
    directories = [
        'data',           # 데이터 파일들
        'models',         # LLM 모델 파일
        'data/vector_index'  # RAG 시스템의 벡터 인덱스
    ]
    
    # 디렉토리 생성
    for directory in directories:
        dir_path = os.path.join(root_dir, directory)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"생성된 디렉토리: {dir_path}")
        else:
            print(f"이미 존재하는 디렉토리: {dir_path}")

if __name__ == "__main__":
    setup_project_structure() 