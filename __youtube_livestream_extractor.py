import os
import json
import time
import requests
import re
from datetime import datetime
import base64
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

# GitHub APIの設定
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def get_video_transcript(video_id):
    """YouTubeビデオの文字起こしを取得する（youtube-transcript-api使用）"""
    print(f"ビデオID: {video_id} の文字起こしを取得します（youtube-transcript-api使用）")
    
    try:
        # 字幕を取得
        print("字幕を取得しています...")
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 日本語の字幕を優先的に探す
        transcript = None
        try:
            transcript = transcript_list.find_transcript(['ja'])
            print("日本語の字幕が見つかりました")
        except:
            # 日本語が見つからない場合は、利用可能な最初の字幕を使用
            print("日本語の字幕が見つかりませんでした。利用可能な字幕を探します...")
            for available_transcript in transcript_list:
                transcript = available_transcript
                print(f"字幕が見つかりました: {transcript.language}")
                break
        
        if not transcript:
            print(f"ビデオ {video_id} に字幕が見つかりませんでした")
            return ""
        
        # 字幕をテキスト形式に変換
        formatter = TextFormatter()
        transcript_text = formatter.format_transcript(transcript.fetch())
        
        print(f"文字起こしテキストの長さ: {len(transcript_text)} 文字")
        return transcript_text
        
    except Exception as e:
        print(f"字幕取得中にエラーが発生しました: {str(e)}")
        return ""

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
    
    # データの完全な内容を出力（デバッグ用）
    print("livestreams.jsonの完全な内容:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    
    # データが辞書型の場合、適切な形式に変換
    if isinstance(data, dict):
        # 辞書のキーと値を確認
        print("辞書のキー:", list(data.keys()))
        
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
        
        # 'livestreams'キーがあれば、その値を使用
        if 'livestreams' in data:
            print("'livestreams'キーが見つかりました。その値を使用します。")
            livestreams = data['livestreams']
            if isinstance(livestreams, list):
                return livestreams
            else:
                print(f"'livestreams'の値がリストではありません: {type(livestreams)}")
        
        # 辞書の値の中からURLやvideoIdを含む項目を探す
        video_items = []
        for key, value in data.items():
            if isinstance(value, dict) and ('url' in value or 'videoId' in value):
                print(f"キー '{key}' に動画情報が見つかりました")
                video_items.append(value)
            elif isinstance(value, str) and ('youtube.com' in value or 'youtu.be' in value):
                print(f"キー '{key}' にYouTube URLが見つかりました: {value}")
                video_items.append(value)
        
        if video_items:
            print(f"{len(video_items)}個の動画情報が見つかりました")
            return video_items
        
        # 最後の手段として、辞書の値をリストとして返す
        print("適切な動画情報が見つからなかったため、辞書の値をリストとして使用します")
        return list(data.values())
    
    return data

def save_transcript_to_file(video_id, transcript, video_title, output_dir="transcripts"):
    """文字起こしをローカルファイルに保存する"""
    # ディレクトリが存在しない場合は作成
    os.makedirs(output_dir, exist_ok=True)
    
    # ファイル名とコンテンツを準備
    file_path = os.path.join(output_dir, f"{video_id}.md")
    
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
    
    print(f"文字起こしを {file_path} に保存しました")
    return True

def check_transcript_exists(video_id, output_dir="transcripts"):
    """指定されたビデオIDの文字起こしファイルが既に存在するか確認する"""
    file_path = os.path.join(output_dir, f"{video_id}.md")
    exists = os.path.exists(file_path)
    print(f"文字起こしファイル {file_path} の存在確認: {exists}")
    return exists

def get_video_title(video_id):
    """YouTubeビデオのタイトルを取得する（シンプルなHTTPリクエスト使用）"""
    print(f"ビデオID: {video_id} のタイトルを取得します")
    
    try:
        # YouTubeのOEmbedエンドポイントを使用してタイトルを取得
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            title = data.get("title", f"Video {video_id}")
            print(f"ビデオタイトル: {title}")
            return title
        else:
            print(f"タイトル取得に失敗しました: {response.status_code}")
            return f"Video {video_id}"
    except Exception as e:
        print(f"タイトル取得中にエラーが発生しました: {str(e)}")
        return f"Video {video_id}"

def create_sample_transcript():
    """サンプルの文字起こしファイルを作成する（APIが失敗した場合のフォールバック）"""
    print("サンプルの文字起こしファイルを作成します")
    video_id = "sample_video_id"
    video_title = "サンプル動画タイトル"
    transcript = """これはサンプルの文字起こしテキストです。

実際のYouTube APIからの文字起こしが取得できなかったため、このサンプルファイルが生成されました。

考えられる原因:
1. 対象の動画に字幕が存在しない
2. youtube-transcript-apiでエラーが発生した
3. livestreams.jsonファイルの形式が想定と異なる

ログファイルを確認して、詳細なエラー情報を確認してください。
"""
    
    save_transcript_to_file(video_id, transcript, video_title)
    print("サンプルファイルの作成が完了しました")

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

def main():
    print("YouTube文字起こし処理を開始します")
    
    # 環境変数の確認
    if not GITHUB_TOKEN:
        print("GITHUB_TOKENが設定されていません")
    else:
        print("GITHUB_TOKENが設定されています")
    
    # リポジトリ情報
    source_owner = "paji"
    source_repo = "82ch"
    source_path = "livestreams.json"
    
    # ライブストリーム一覧を取得
    livestreams = get_livestreams_from_repo(source_owner, source_repo, source_path)
    
    if not livestreams:
        print("ライブストリームが見つかりませんでした")
        print("サンプルの文字起こしファイルを作成します")
        create_sample_transcript()
        return
    
    processed = False
    
    # 処理するエピソードを1つ選択（既に処理済みのものはスキップ）
    print(f"処理するライブストリーム: {len(livestreams)}件")
    
    for i, stream in enumerate(livestreams):
        print(f"ライブストリーム {i+1}/{len(livestreams)} を処理します")
        print(f"ストリームデータ: {stream}")
        
        # streamが文字列の場合（URLそのもの）とオブジェクトの場合の両方に対応
        video_id = None
        if isinstance(stream, dict):
            print("ストリームはディクショナリ形式です")
            # videoIdフィールドを確認
            if 'videoId' in stream:
                video_id = stream['videoId']
                print(f"videoIdフィールドから取得: {video_id}")
            # urlフィールドを確認
            elif 'url' in stream:
                video_id = extract_video_id(stream['url'])
                print(f"urlフィールドからビデオIDを抽出: {video_id}")
            # idフィールドを確認
            elif 'id' in stream:
                video_id = stream['id']
                print(f"idフィールドから取得: {video_id}")
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
        
        # 文字起こしを取得
        transcript = get_video_transcript(video_id)
        
        if not transcript:
            print(f"ビデオID {video_id} の文字起こしが利用できません。スキップします")
            continue
        
        # ビデオタイトルを取得
        video_title = get_video_title(video_id)
        
        # 文字起こしを保存
        success = save_transcript_to_file(video_id, transcript, video_title)
        
        if success:
            print(f"ビデオID {video_id} の処理が成功しました")
            processed = True
            # 1時間に1件のみ処理するため、1件処理したら終了
            break
        else:
            print(f"ビデオID {video_id} の処理に失敗しました")
    
    if not processed:
        print("処理可能なライブストリームが見つかりませんでした")
        print("サンプルの文字起こしファイルを作成します")
        create_sample_transcript()
    
    print("処理が完了しました")

if __name__ == "__main__":
    main()
