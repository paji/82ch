import os
import json
import time
import requests
import google.oauth2.credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import re
from datetime import datetime
import base64

# GitHub APIの設定
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# YouTubeの設定
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

def get_youtube_service():
    """YouTube Data API v3のサービスを取得する"""
    return build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

def get_video_transcript(video_id):
    """YouTubeビデオの文字起こしを取得する"""
    youtube = get_youtube_service()
    
    try:
        # 字幕トラックの一覧を取得
        captions_response = youtube.captions().list(
            part="snippet",
            videoId=video_id
        ).execute()
        
        # 字幕がない場合は空の文字列を返す
        if not captions_response.get("items"):
            print(f"No captions found for video {video_id}")
            return ""
        
        # 日本語の字幕を優先的に探す
        caption_id = None
        for item in captions_response.get("items", []):
            language = item["snippet"]["language"]
            if language == "ja":
                caption_id = item["id"]
                break
        
        # 日本語の字幕がなければ最初の字幕を使用
        if not caption_id and captions_response.get("items"):
            caption_id = captions_response["items"][0]["id"]
        
        if not caption_id:
            print(f"No suitable captions found for video {video_id}")
            return ""
        
        # 字幕コンテンツを取得
        transcript_response = youtube.captions().download(
            id=caption_id,
            tfmt="srt"
        ).execute()
        
        # SRT形式から純粋なテキストに変換
        transcript_text = clean_srt(transcript_response.decode('utf-8'))
        return transcript_text
        
    except HttpError as e:
        print(f"An HTTP error {e.resp.status} occurred: {e.content}")
        return ""

def clean_srt(srt_text):
    """SRT形式から時間コードを削除し、純粋なテキストを抽出する"""
    # 時間コードと番号を削除
    lines = srt_text.split('\n')
    cleaned_lines = []
    skip_next = False
    
    for i, line in enumerate(lines):
        # 数字だけの行（字幕番号）をスキップ
        if re.match(r'^\d+$', line.strip()):
            skip_next = True
            continue
        
        # 時間コード行をスキップ
        if skip_next or re.match(r'^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$', line.strip()):
            skip_next = False
            continue
        
        # 空行でなければ追加
        if line.strip():
            cleaned_lines.append(line)
    
    # 連続する空行を1つにまとめる
    text = '\n'.join(cleaned_lines)
    text = re.sub(r'\n{2,}', '\n\n', text)
    
    return text.strip()

def get_livestreams_from_repo(owner, repo, path):
    """GitHubリポジトリからライブストリームのJSONを取得する"""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    response = requests.get(url, headers=GITHUB_HEADERS)
    
    if response.status_code != 200:
        print(f"Failed to get file from GitHub: {response.status_code}")
        return []
    
    content = response.json()
    file_content = base64.b64decode(content["content"]).decode("utf-8")
    return json.loads(file_content)

def save_transcript_to_file(video_id, transcript, video_title):
    """文字起こしをローカルファイルに保存する"""
    # ディレクトリが存在しない場合は作成
    os.makedirs("youtube_text", exist_ok=True)
    
    # ファイル名とコンテンツを準備
    file_path = os.path.join("youtube_text", f"{video_id}.md")
    
    # マークダウンヘッダーを追加
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = f"""# {video_title}

Video ID: {video_id}
Transcribed at: {current_time}

## Transcript

{transcript}
"""
    
    # ファイルに書き込み
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"Successfully saved transcript to {file_path}")
    return True

def check_transcript_exists(video_id):
    """指定されたビデオIDの文字起こしファイルが既に存在するか確認する"""
    file_path = os.path.join("youtube_text", f"{video_id}.md")
    return os.path.exists(file_path)

def get_video_title(video_id):
    """YouTubeビデオのタイトルを取得する"""
    youtube = get_youtube_service()
    
    try:
        response = youtube.videos().list(
            part="snippet",
            id=video_id
        ).execute()
        
        if response["items"]:
            return response["items"][0]["snippet"]["title"]
        return f"Video {video_id}"
    except HttpError as e:
        print(f"An HTTP error {e.resp.status} occurred: {e.content}")
        return f"Video {video_id}"

def main():
    # 環境変数の確認
    if not YOUTUBE_API_KEY:
        print("YOUTUBE_API_KEY is not set")
        return
    
    # リポジトリ情報
    source_owner = "paji"
    source_repo = "82ch"
    source_path = "livestreams.json"
    
    # ライブストリーム一覧を取得
    livestreams = get_livestreams_from_repo(source_owner, source_repo, source_path)
    
    if not livestreams:
        print("No livestreams found")
        return
    
    # 処理するエピソードを1つ選択（既に処理済みのものはスキップ）
    for stream in livestreams:
        # streamが文字列の場合（URLそのもの）とオブジェクトの場合の両方に対応
        if isinstance(stream, dict):
            video_id = stream.get("videoId") or extract_video_id(stream.get("url", ""))
        else:
            # streamが文字列の場合はURLとして扱う
            video_id = extract_video_id(stream)
        
        if not video_id:
            print(f"Could not extract video ID from {stream}")
            continue
        
        # 既に文字起こしが存在するかチェック
        if check_transcript_exists(video_id):
            print(f"Transcript for {video_id} already exists, skipping")
            continue
        
        # 文字起こしを取得
        transcript = get_video_transcript(video_id)
        
        if not transcript:
            print(f"No transcript available for {video_id}, skipping")
            continue
        
        # ビデオタイトルを取得
        video_title = get_video_title(video_id)
        
        # 文字起こしを保存
        success = save_transcript_to_file(video_id, transcript, video_title)
        
        if success:
            print(f"Successfully processed {video_id}")
            # 1時間に1件のみ処理するため、1件処理したら終了
            break
        else:
            print(f"Failed to process {video_id}")
    
    print("Processing completed")

def extract_video_id(url):
    """YouTubeのURLからビデオIDを抽出する"""
    if not url:
        return None
    
    # 通常のYouTube URL
    match = re.search(r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)
    
    return None

if __name__ == "__main__":
    main()
