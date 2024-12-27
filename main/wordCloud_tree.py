from flask import Flask, send_file, jsonify
from flask_cors import CORS
from wordcloud import WordCloud
from collections import Counter
from PIL import Image
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
import numpy as np
import re
import random
import requests
import os
import html
import logging


# 로그 설정
handler = RotatingFileHandler("server.log", maxBytes=1024 * 1024, backupCount=5)  # 1MB 크기, 5개의 백업 로그 유지
logging.basicConfig(
    level=logging.INFO,  # 로그 레벨 설정 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[handler, logging.StreamHandler()]  # 파일 및 콘솔 로그 출력
)

# Flask 앱 생성 및 CORS 설정
app = Flask(__name__)
CORS(app)

# .env 파일 로드
load_dotenv()

# 환경 변수에서 API 인증 정보 가져오기
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# 프로젝트 디렉토리 및 리소스 경로 설정
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
FONT_PATH = os.path.join(BASE_DIR, "../font", "NotoSansKR-VariableFont_wght.ttf")  # 폰트 파일 경로
MASK_IMAGE_PATH = os.path.join(BASE_DIR, "../image", "Recycle.png")               # 마스크 이미지 경로

# 워드클라우드 색상 설정
recycle_colors = ["#008000", "#0000FF", "#FFAA00"]
def recycle_colors_func(word, font_size, position, orientation, random_state=None, **kwargs):
    # 워드클라우드 텍스트에 초록색, 파란색, 주황색 랜덤 적용
    return random.choice(recycle_colors)

# 네이버 뉴스 데이터 가져오기
def fetch_naver_news(display=5):
    keyword = "분리수거"  # 검색 키워드
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": CLIENT_ID,  # 네이버 API 클라이언트 ID
        "X-Naver-Client-Secret": CLIENT_SECRET  # 네이버 API 클라이언트 Secret
    }
    params = {
        "query": keyword,  # 검색어
        "display": display,  # 가져올 뉴스 개수
        "start": 1,         # 검색 시작 위치
        "sort": "date"      # 최신순 정렬
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()  # HTTP 요청 성공 여부 확인
        data = response.json()
        logging.info(f"네이버 뉴스 API 요청 성공")
        return data["items"]  # 뉴스 데이터 반환
    except requests.exceptions.RequestException as e:
        logging.error(f"네이버 뉴스 API 요청 실패: {e}")
        return []  # 실패 시 빈 리스트 반환

# 텍스트 전처리 및 명사 추출
def preprocess_text(text):
    tokens = re.findall(r'\b[가-힣]{2,}\b', text)  # 한글 단어 추출
    stop_words = {"것", "수", "있다", "하다", "의", "를", "이", "에", "가", "은", "들", "에서"}  # 불용어 제거
    word_freq = Counter([word for word in tokens if word not in stop_words])  # 단어 빈도 계산
    return word_freq

# 워드클라우드 생성 함수
def generate_wordcloud(word_freq, output_path):
    try:
        mask = np.array(Image.open(MASK_IMAGE_PATH))  # 마스크 이미지 로드
        wordcloud = WordCloud(
            font_path=FONT_PATH,  # 워드클라우드에 사용할 폰트
            background_color="white",  # 배경색 설정
            mask=mask,  # 마스크 이미지 적용
            color_func=recycle_colors_func  # 색상 설정
        ).generate_from_frequencies(word_freq)
        wordcloud.to_file(output_path)  # 워드클라우드 이미지 파일로 저장
        logging.info("워드클라우드 이미지 생성 완료")
    except Exception as e:
        logging.error(f"Failed to generate wordcloud: {e}")

# 메인 페이지 라우트
@app.route("/", methods=["GET"])
def home():
    return """
    <h1>API Server</h1>
    <p>Endpoints:</p>
    <ul>
        <li>/api/wordcloud - 워드클라우드 이미지</li>
        <li>/api/news - 뉴스 리스트</li>
    </ul>
    """

# 워드클라우드 생성 API
@app.route("/api/wordcloud", methods=["GET"])
def wordcloud_endpoint():
    logging.info("워드클라우드 생성 요청을 처리합니다.")
    descriptions = [item["description"] for item in fetch_naver_news(display=5)]  # 뉴스 내용 추출

    if not descriptions:  # 뉴스 데이터가 없으면 에러 반환
        return jsonify({"error": "기사를 가져올 수 없습니다."}), 500

    combined_text = " ".join(descriptions)  # 모든 뉴스 내용을 합침
    word_freq = preprocess_text(combined_text)  # 텍스트 전처리
    output_path = "wordcloud.png"  # 워드클라우드 출력 파일 경로
    generate_wordcloud(word_freq, output_path)  # 워드클라우드 생성

    return send_file(output_path, mimetype="image/png")  # 생성된 이미지를 반환

# 뉴스 리스트 API
@app.route("/api/news", methods=["GET"])
def news_endpoint():
    logging.info("뉴스 리스트 요청을 처리합니다.")
    articles = fetch_naver_news(display=10)  # 최대 10개의 뉴스 가져오기

    if not articles:  # 뉴스 데이터가 없으면 에러 반환
        return jsonify({"error": "기사를 가져올 수 없습니다."}), 500

    # 중복 제거를 위한 Set 사용
    seen_titles = set()
    news_list = []
    for item in articles:
        title = html.unescape(item["title"].replace("<b>", "").replace("</b>", ""))  # 제목 정리
        if title not in seen_titles:  # 중복된 제목 제거
            seen_titles.add(title)
            news_list.append({
                "title": title,  # 기사 제목
                "link": item["link"]  # 기사 링크
            })

    return jsonify(news_list)  # JSON으로 뉴스 리스트 반환

# Flask 서버 실행
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)  # 서버 실행