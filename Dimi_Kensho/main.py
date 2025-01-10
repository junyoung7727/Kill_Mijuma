import json
import os
from sec_fetcher import SECFetcher
from llm_translate import extract_all_tags, get_llm_translations, create_structured_json
from create_html import create_kr_html
from setup import setup_project_structure

def ensure_data_directory():
    """데이터 디렉토리 생성"""
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    return data_dir

def main():
    # 프로젝트 구조 설정
    setup_project_structure()
    
    # 데이터 디렉토리 확인
    data_dir = ensure_data_directory()
    
    # SEC Fetcher 초기화
    fetcher = SECFetcher('junghae2017@gmail.com', data_dir)
    
    # URL 설정
    url = "https://www.sec.gov/ix?doc=/Archives/edgar/data/320193/000032019324000006/aapl-20231230.htm"
    
    # XBRL 데이터 가져오기
    print("\n1. XBRL 데이터 가져오기...")
    xbrl_data = fetcher.get_xbrl_data(url)
    if not xbrl_data:
        print("XBRL 데이터 가져오기 실패")
        return
    print("XBRL 데이터 가져오기 완료")
    
    # 데이터 통합
    integrated_data = fetcher.integrate_data()
    
    # 계층 구조 생성 및 저장
    print("\n2. 계층 구조 생성...")
    hierarchy = fetcher.create_hierarchy_json(xbrl_data, integrated_data)
    if not hierarchy:
        print("계층 구조 생성 실패")
        return
    print("계층 구조 생성 완료")
    
    try:
        # 태그 추출 및 필터링
        print("\n3. 태그 추출 및 필터링 시작...")
        tags_list, filtered_hierarchy = extract_all_tags(data_dir)
        print("태그 추출 완료")
        
        # LLM 번역 수행
        print("\n4. LLM 번역 시작...")
        translations = get_llm_translations(tags_list, data_dir)
        print("번역 완료")
        
        # 구조화된 JSON 생성
        print("\n5. 구조화된 JSON 생성 시작...")
        structured_data = create_structured_json(translations, filtered_hierarchy, data_dir)
        print("JSON 생성 완료")
        
        # HTML 생성
        print("\n6. HTML 생성 시작...")
        create_kr_html(data_dir)
        print("HTML 생성 완료")
        
        print("\n모든 프로세스가 성공적으로 완료되었습니다.")
        print("생성된 파일:")
        print(f"- {os.path.join(data_dir, 'hierarchy.json')}")
        print(f"- {os.path.join(data_dir, 'hierarchy_filtered.json')}")
        print(f"- {os.path.join(data_dir, 'tags_for_translation.json')}")
        print(f"- {os.path.join(data_dir, 'translated_tags.json')}")
        print(f"- {os.path.join(data_dir, 'structured_kr_data.json')}")
        print(f"- {os.path.join(data_dir, 'xbrl_visualization_kr.html')}")
        
    except Exception as e:
        print(f"\n처리 중 오류 발생: {str(e)}")
        return

if __name__ == "__main__":
    main()