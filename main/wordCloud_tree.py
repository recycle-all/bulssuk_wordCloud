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
from datetime import datetime, timedelta

# 로그 설정
handler = RotatingFileHandler("server.log", maxBytes=1024 * 1024, backupCount=5)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[handler, logging.StreamHandler()]
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
FONT_PATH = os.path.join(BASE_DIR, "../font", "NotoSansKR-VariableFont_wght.ttf")
MASK_IMAGE_PATH = os.path.join(BASE_DIR, "../image", "Recycle.png")

# 워드클라우드 색상 설정
recycle_colors = ["#008000", "#0000FF", "#FFAA00"]
def recycle_colors_func(word, font_size, position, orientation, random_state=None, **kwargs):
    return random.choice(recycle_colors)

# 전역 변수: 마지막 업데이트 시간
last_updated = None  # 마지막 업데이트 시간을 저장

# 네이버 뉴스 데이터 가져오기
def fetch_naver_news(display=10):
    keyword = "분리수거"
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET
    }
    params = {
        "query": keyword,
        "display": display,
        "start": 1,
        "sort": "date"
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        logging.info(f"네이버 뉴스 API 요청 성공, 가져온 기사 개수: {len(data['items'])}")
        return data["items"]
    except requests.exceptions.RequestException as e:
        logging.error(f"네이버 뉴스 API 요청 실패: {e}")
        return []

# 텍스트 전처리 및 명사 추출
def preprocess_text(text):
    tokens = re.findall(r'\b[가-힣]{2,}\b', text)
    stop_words = {"것", "수", "있다", "하다", "의", "를", "이", "에", "가", "은", "들", "에서"}
    word_freq = Counter([word for word in tokens if word not in stop_words])
    return word_freq

# 워드클라우드 생성 함수
def generate_wordcloud(word_freq, output_path):
    try:
        mask = np.array(Image.open(MASK_IMAGE_PATH))
        wordcloud = WordCloud(
            font_path=FONT_PATH,
            background_color="white",
            mask=mask,
            color_func=recycle_colors_func
        ).generate_from_frequencies(word_freq)
        wordcloud.to_file(output_path)
        logging.info("워드클라우드 이미지 생성 완료")
    except Exception as e:
        logging.error(f"워드클라우드 생성 실패: {e}")

# 워드클라우드와 기사를 업데이트하는 함수
def update_content():
    global last_updated
    now = datetime.now()

    # 오전 6시 이후이고, 이전 업데이트가 없거나 하루가 지났다면 업데이트
    if not last_updated or now >= last_updated + timedelta(days=1):
        logging.info("컨텐츠 업데이트 시작")
        descriptions = [item["description"] for item in fetch_naver_news(display=10)]

        if descriptions:
            combined_text = " ".join(descriptions)
            word_freq = preprocess_text(combined_text)
            generate_wordcloud(word_freq, "wordcloud.png")
            last_updated = now.replace(hour=6, minute=0, second=0, microsecond=0)
            logging.info(f"컨텐츠 업데이트 완료: {last_updated}")
        else:
            logging.error("네이버 뉴스 데이터를 가져오지 못했습니다.")

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

# 워드클라우드 API
@app.route("/api/wordcloud", methods=["GET"])
def wordcloud_endpoint():
    update_content()  # 필요 시 컨텐츠 업데이트
    return send_file("wordcloud.png", mimetype="image/png")

# 뉴스 리스트 API
@app.route("/api/news", methods=["GET"])
def news_endpoint():
    articles = fetch_naver_news(display=10)  # 최대 10개의 기사 요청

    if not articles:
        return jsonify({"error": "기사를 가져올 수 없습니다."}), 500

    # 중복 제거 없이 모든 기사 반환
    news_list = [{
        "title": html.unescape(item["title"].replace("<b>", "").replace("</b>", "")),
        "link": item["link"]
    } for item in articles]

    logging.info(f"최종 반환된 기사 개수: {len(news_list)}")
    return jsonify(news_list)


if __name__ == "__main__":
    import sys
    import os

    # 서버 중복 실행 방지
    try:
        update_content()  # 서버 시작 시 즉시 업데이트
        app.run(debug=True, host="0.0.0.0", port=5002)
    except OSError as e:
        if "Address already in use" in str(e):
            print("포트 5002가 이미 사용 중입니다. 서버가 이미 실행 중일 수 있습니다.")
            sys.exit(1)
        else:
            raise e