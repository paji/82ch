import os
import json
import time
import requests
import re
from datetime import datetime
from groq import Groq
import base64
import sys

# 環境変数からAPIキーを取得
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# GitHubのヘッダー設定
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def get_livestreams_from_repo(owner, repo, path):
    """GitHubリポジトリからライブストリームのJSONを取得する"""
    print(f"GitHubリポジトリ {owner}/{repo} から {path} を取得しています")
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    response = requests.get(url, headers=GITHUB_HEADERS)
    
    if response.status_code != 200:
        print(f"GitHubからファイルの取得に失敗しました: {response.status_code}")
        print(f"レスポンス内容: {response.text}")
        return []
    
    content = response.json()
    file_content = base64.b64decode(content["content"]).decode("utf-8")
    data = json.loads(file_content)
    print(f"取得したデータ: {type(data)}, 要素数: {len(data) if isinstance(data, list) else 'Not a list'}")
    
    # データが辞書型の場合、適切な形式に変換
    if isinstance(data, dict):
        # 辞書のキーと値を確認
        print("辞書のキー:", list(data.keys()))
        
        # 'livestreams'キーがあれば、その値を使用
        if 'livestreams' in data:
            print("'livestreams'キーが見つかりました。その値を使用します。")
            livestreams = data['livestreams']
            if isinstance(livestreams, list):
                return livestreams
            else:
                print(f"'livestreams'の値がリストではありません: {type(livestreams)}")
        
        # 'episodes'キーがあれば、その値を使用
        if 'episodes' in data:
            print("'episodes'キーが見つかりました。その値を使用します。")
            episodes = data['episodes']
            if isinstance(episodes, list):
                return episodes
            else:
                print(f"'episodes'の値がリストではありません: {type(episodes)}")
        
        # 'videos'キーがあれば、その値を使用
        if 'videos' in data:
            print("'videos'キーが見つかりました。その値を使用します。")
            videos = data['videos']
            if isinstance(videos, list):
                return videos
            else:
                print(f"'videos'の値がリストではありません: {type(videos)}")
    
    return data

def extract_video_id(url):
    """YouTubeのURLからビデオIDを抽出する"""
    if not url:
        return None
    
    print(f"URLからビデオIDを抽出します: {url}")
    
    # 通常のYouTube URL
    match = re.search(r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})', url)
    if match:
        video_id = match.group(1)
        print(f"抽出されたビデオID: {video_id}")
        return video_id
    
    print("URLからビデオIDを抽出できませんでした")
    return None

def get_video_info(video_id):
    """YouTubeビデオの情報を取得する（YouTube Data API使用）"""
    print(f"ビデオID: {video_id} の情報を取得します")
    
    try:
        # YouTubeのOEmbedエンドポイントを使用してタイトルを取得
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            title = data.get("title", f"Video {video_id}")
            print(f"ビデオタイトル: {title}")
            return {
                "title": title,
                "id": video_id
            }
        else:
            print(f"タイトル取得に失敗しました: {response.status_code}")
            return {
                "title": f"Video {video_id}",
                "id": video_id
            }
    except Exception as e:
        print(f"タイトル取得中にエラーが発生しました: {str(e)}")
        return {
            "title": f"Video {video_id}",
            "id": video_id
        }

def transcribe_audio_with_groq(audio_url, language="ja"):
    """Groq APIを使用して音声URLを文字起こしする"""
    print(f"Groq APIを使用して音声URL {audio_url} の文字起こしを開始します")
    
    if not GROQ_API_KEY:
        print("GROQ_API_KEYが設定されていません。環境変数を設定してください。")
        return None
    
    try:
        # Groqクライアントを初期化
        client = Groq(api_key=GROQ_API_KEY)
        
        # 文字起こしを実行
        print(f"文字起こしを実行中... (言語: {language})")
        transcription = client.audio.transcriptions.create(
            url=audio_url,
            model="whisper-large-v3-turbo",  # 高速な多言語モデル
            language=language,
            response_format="verbose_json",  # タイムスタンプ付きの詳細なJSON形式
            timestamp_granularities=["segment", "word"]  # セグメントと単語レベルのタイムスタンプ
        )
        
        print("文字起こしが完了しました")
        return transcription
    
    except Exception as e:
        print(f"文字起こし中にエラーが発生しました: {str(e)}")
        return None

def format_timestamp(seconds):
    """秒数をHH:MM:SS形式に変換"""
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def save_transcript_to_file(video_id, transcription, video_title, output_dir="transcripts"):
    """文字起こし結果をファイルに保存する"""
    # ディレクトリが存在しない場合は作成
    os.makedirs(output_dir, exist_ok=True)
    
    # JSONファイルパス（詳細な情報を保存）
    json_file_path = os.path.join(output_dir, f"{video_id}_full.json")
    
    # マークダウンファイルパス（読みやすいテキスト形式）
    md_file_path = os.path.join(output_dir, f"{video_id}.md")
    
    try:
        # JSONファイルに詳細な文字起こし結果を保存
        with open(json_file_path, "w", encoding="utf-8") as f:
            if isinstance(transcription, dict):
                json.dump(transcription, f, ensure_ascii=False, indent=2)
            else:
                # オブジェクトの場合は辞書に変換
                json.dump(transcription.model_dump(), f, ensure_ascii=False, indent=2)
        
        print(f"詳細な文字起こし結果を {json_file_path} に保存しました")
        
        # マークダウンファイルに読みやすい形式で保存
        with open(md_file_path, "w", encoding="utf-8") as f:
            # マークダウンヘッダー
            f.write(f"# {video_title}\n\n")
            f.write(f"Video ID: {video_id}\n")
            f.write(f"Transcribed at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Transcription by: Groq API (whisper-large-v3-turbo)\n\n")
            
            f.write("## 文字起こし\n\n")
            
            # テキスト本文
            if isinstance(transcription, dict) and "segments" in transcription:
                # セグメント単位でタイムスタンプ付きで書き出し
                for segment in transcription["segments"]:
                    start_time = format_timestamp(segment.get("start", 0))
                    end_time = format_timestamp(segment.get("end", 0))
                    text = segment.get("text", "").strip()
                    f.write(f"[{start_time} --> {end_time}] {text}\n\n")
            else:
                # シンプルなテキスト形式
                if isinstance(transcription, dict):
                    f.write(transcription.get("text", ""))
                else:
                    f.write(transcription.text)
        
        print(f"読みやすい文字起こし結果を {md_file_path} に保存しました")
        return True
    
    except Exception as e:
        print(f"文字起こし結果の保存中にエラーが発生しました: {str(e)}")
        return False

def check_transcript_exists(video_id, output_dir="transcripts"):
    """指定されたビデオIDの文字起こしファイルが既に存在するか確認する"""
    file_path = os.path.join(output_dir, f"{video_id}.md")
    exists = os.path.exists(file_path)
    print(f"文字起こしファイル {file_path} の存在確認: {exists}")
    return exists

def main():
    print("Groq APIを使用したYouTube文字起こし処理を開始します")
    
    # 環境変数の確認
    if not GITHUB_TOKEN:
        print("GITHUB_TOKENが設定されていません")
        sys.exit(1)
    else:
        print("GITHUB_TOKENが設定されています")
    
    if not GROQ_API_KEY:
        print("GROQ_API_KEYが設定されていません")
        sys.exit(1)
    else:
        print("GROQ_API_KEYが設定されています")
    
    # リポジトリ情報
    source_owner = "paji"
    source_repo = "82ch"
    source_path = "livestreams.json"
    
    # ライブストリーム一覧を取得
    livestreams = get_livestreams_from_repo(source_owner, source_repo, source_path)
    
    if not livestreams:
        print("ライブストリームが見つかりませんでした")
        sys.exit(1)
    
    # 処理するエピソードを1つ選択（既に処理済みのものはスキップ）
    print(f"処理するライブストリーム: {len(livestreams)}件")
    
    # 1時間に1件のみ処理するためのフラグ
    processed = False
    
    for i, stream in enumerate(livestreams):
        print(f"ライブストリーム {i+1}/{len(livestreams)} を処理します")
        print(f"ストリームデータ: {stream}")
        
        # streamが文字列の場合（URLそのもの）とオブジェクトの場合の両方に対応
        video_id = None
        if isinstance(stream, dict):
            print("ストリームはディクショナリ形式です")
            # videoIdフィールドを確認
            if 'id' in stream:
                video_id = stream['id']
                print(f"idフィールドから取得: {video_id}")
            # urlフィールドを確認
            elif 'url' in stream:
                video_id = extract_video_id(stream['url'])
                print(f"urlフィールドからビデオIDを抽出: {video_id}")
            # その他のフィールドを確認
            else:
                for key, value in stream.items():
                    if isinstance(value, str) and ('youtube.com' in value or 'youtu.be' in value):
                        video_id = extract_video_id(value)
                        print(f"フィールド '{key}' からビデオIDを抽出: {video_id}")
                        if video_id:
                            break
        else:
            # streamが文字列の場合はURLとして扱う
            print("ストリームは文字列形式です")
            if 'youtube.com' in stream or 'youtu.be' in stream:
                video_id = extract_video_id(stream)
            else:
                print(f"文字列 '{stream}' はYouTube URLではありません")
        
        if not video_id:
            print(f"ストリーム {stream} からビデオIDを抽出できませんでした")
            continue
        
        # 既に文字起こしが存在するかチェック
        if check_transcript_exists(video_id):
            print(f"ビデオID {video_id} の文字起こしは既に存在します。スキップします")
            continue
        
        # ビデオ情報を取得
        video_info = None
        if isinstance(stream, dict) and 'title' in stream:
            video_title = stream['title']
            print(f"ストリームデータからタイトルを取得: {video_title}")
            video_info = {"title": video_title, "id": video_id}
        else:
            video_info = get_video_info(video_id)
        
        if not video_info:
            print(f"ビデオID {video_id} の情報取得に失敗しました。スキップします")
            continue
        
        # 直接YouTubeからダウンロードせず、Groq APIにURLを渡す
        audio_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # 文字起こしを実行
        transcription = transcribe_audio_with_groq(audio_url)
        if not transcription:
            print(f"ビデオID {video_id} の文字起こしに失敗しました。スキップします")
            continue
        
        # 文字起こし結果を保存
        success = save_transcript_to_file(video_id, transcription, video_info["title"])
        
        if success:
            print(f"ビデオID {video_id} の処理が成功しました")
            processed = True
            # 1時間に1件のみ処理するため、1件処理したら終了
            print("1時間に1件のみ処理するため、処理を終了します")
            break
        else:
            print(f"ビデオID {video_id} の処理に失敗しました")
    
    if not processed:
        print("処理可能なライブストリームが見つかりませんでした")
    
    print("処理が完了しました")

if __name__ == "__main__":
    main()
