import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import traceback

class ContextVisualizer:
    def __init__(self, context_file_path: str):
        """
        컨텍스트 시각화를 위한 클래스를 초기화합니다.
        
        Args:
            context_file_path (str): context_data.json 파일의 경로
        """
        self.context_file_path = context_file_path
        self.context_data = self._load_context_data()
    
    def _load_context_data(self) -> list:
        """context_data.json 파일을 로드합니다."""
        try:
            with open(self.context_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"컨텍스트 데이터 로드 중 오류: {str(e)}")
            return []

    def visualize_timeline(self):
        """컨텍스트의 기간을 타임라인으로 시각화합니다."""
        try:
            # 컨텍스트 데이터 수집
            periods = []  # 기간 데이터
            instants = []  # 순간 데이터
            
            for context_id, context_data in self.context_data.items():
                if context_data.get('type') == 'period':
                    start_date = context_data.get('start_date')
                    end_date = context_data.get('end_date')
                    if start_date and end_date:
                        periods.append({
                            'id': context_id,
                            'start': datetime.strptime(start_date, '%Y-%m-%d'),
                            'end': datetime.strptime(end_date, '%Y-%m-%d')
                        })
                elif context_data.get('type') == 'instant':
                    date = context_data.get('date')
                    if date:
                        instants.append({
                            'id': context_id,
                            'date': datetime.strptime(date, '%Y-%m-%d')
                        })
            
            if not periods and not instants:
                print("표시할 데이터가 없습니다.")
                return
            
            # 그래프 설정
            plt.figure(figsize=(15, 8))
            
            current_y = 0  # y축 위치 카운터
            
            # 기간 데이터 표시
            for ctx in periods:
                plt.hlines(y=current_y, xmin=ctx['start'], xmax=ctx['end'], 
                          linewidth=4, color='royalblue', alpha=0.7)
                plt.plot(ctx['start'], current_y, 'o', color='royalblue', alpha=0.7)
                plt.plot(ctx['end'], current_y, 'o', color='royalblue', alpha=0.7)
                
                # 기간 텍스트 표시
                duration = (ctx['end'] - ctx['start']).days
                mid_point = ctx['start'] + (ctx['end'] - ctx['start'])/2
                plt.text(mid_point, current_y+0.1, f'{duration}일', 
                        ha='center', va='bottom')
                
                # 컨텍스트 ID 표시
                plt.text(ctx['start'], current_y-0.2, f'Context: {ctx["id"]} (period)', 
                        ha='left', va='top')
                
                current_y += 1
            
            # instant 데이터 표시
            for ctx in instants:
                plt.plot(ctx['date'], current_y, 'D', color='red', alpha=0.7, markersize=8)
                
                # 컨텍스트 ID 표시
                plt.text(ctx['date'], current_y-0.2, f'Context: {ctx["id"]} (instant)', 
                        ha='left', va='top')
                
                current_y += 1
            
            # 축 설정
            plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            plt.gcf().autofmt_xdate()  # x축 레이블 회전
            
            # 레이블 설정
            plt.title('컨텍스트 타임라인', pad=20, size=14, weight='bold')
            plt.xlabel('날짜', labelpad=10)
            plt.ylabel('컨텍스트', labelpad=10)
            
            # y축 눈금 제거
            plt.yticks([])
            
            # 범례 추가
            plt.plot([], [], 'D', color='red', alpha=0.7, label='Instant')
            plt.plot([], [], '-', color='royalblue', alpha=0.7, label='Period')
            plt.legend()
            
            # 그리드 추가
            plt.grid(True, axis='x', linestyle='--', alpha=0.7)
            
            # 여백 조정
            plt.tight_layout()
            
            # 저장 및 표시
            plt.savefig('context_timeline.png', dpi=300, bbox_inches='tight')
            plt.show()
            
        except Exception as e:
            print(f"시각화 중 오류 발생: {str(e)}")
            traceback.print_exc()

if __name__ == "__main__":
    # 사용 예시
    visualizer = ContextVisualizer("Dimi_Kensho/data/context_data.json")
    visualizer.visualize_timeline()