#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube動画文字起こしツール

指定されたYouTube動画の文字起こしを取得し、Markdownファイルとして保存します。
"""

import os
import json
import argparse
import logging
import time
from datetime import datetime
from pathlib import Path
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('youtube_transcription')

class YouTubeTranscription:
    """YouTubeの動画文字起こしを取得するクラス"""

    def __init__(self):
        """初期化メソッド"""
        self.transcript_api = YouTubeTranscriptApi()

    def get_video_id_from_url(self, url):
        """
        YouTube動画URLからビデオIDを抽出
        
        Args:
            url (str): YouTube動画のURL
            
        Returns:
            str: ビデオID
        """
        if 'youtube.com/watch?v=' in url:
            return url.split('youtube.com/watch?v=')[1].split('&')[0]
        elif 'youtu.be/' in url:
            return url.split('youtu.be/')[1].split('?')[0]
        else:
            raise ValueError(f"無効なYouTube URL: {url}")

    def get_transcript(self, video_id, languages=['ja', 'en']):
        """
        動画の文字起こしを取得
        
        Args:
            video_id (str): YouTube動画ID
            languages (list): 取得する言語コードのリスト（優先順）
            
        Returns:
            dict: 文字起こし情報
        """
        try:
            # 利用可能な文字起こしリストを取得
            transcript_list = self.transcript_api.list(video_id)
            
            # 指定された言語の文字起こしを検索
            transcript = transcript_list.find_transcript(languages)
            
            # 文字起こしデータを取得
            fetched_transcript = transcript.fetch()
            
            return {
                'video_id': video_id,
                'language': transcript.language,
                'language_code': transcript.language_code,
                'is_generated': transcript.is_generated,
                'transcript': fetched_transcript.to_raw_data()
            }
        except TranscriptsDisabled:
            logger.error(f"動画ID {video_id} の文字起こしは無効になっています")
            return None
        except NoTranscriptFound:
            logger.error(f"動画ID {video_id} の文字起こしが見つかりませんでした")
            return None
        except Exception as e:
            logger.error(f"エラー: {e}")
            return None

    def format_transcript_as_markdown(self, transcript_data, video_info=None):
        """
        文字起こしデータをMarkdown形式にフォーマット
        
        Args:
            transcript_data (dict): 文字起こしデータ
            video_info (dict, optional): 動画情報
            
        Returns:
            str: Markdown形式の文字起こし
        """
        if not transcript_data:
            return None
        
        md_content = []
        
        # ヘッダー情報
        if video_info:
            md_content.append(f"# {video_info['title']}")
            md_content.append("")
            md_content.append(f"- URL: https://www.youtube.com/watch?v={transcript_data['video_id']}")
            md_content.append(f"- チャンネル: {video_info['channelTitle']}")
            md_content.append(f"- 公開日: {video_info['publishedAt'][:10]}")
            md_content.append("")
            
            if video_info.get('description'):
                md_content.append("## 概要")
                md_content.append("")
                md_content.append(video_info['description'])
                md_content.append("")
        else:
            md_content.append(f"# YouTube動画 {transcript_data['video_id']} の文字起こし")
            md_content.append("")
            md_content.append(f"- URL: https://www.youtube.com/watch?v={transcript_data['video_id']}")
            md_content.append(f"- 言語: {transcript_data['language']} ({transcript_data['language_code']})")
            md_content.append(f"- 自動生成: {'はい' if transcript_data['is_generated'] else 'いいえ'}")
            md_content.append("")
        
        # 文字起こし本文
        md_content.append("## 文字起こし")
        md_content.append("")
        
        # 時間でグループ化（5分ごと）
        current_time_group = 0
        current_paragraph = []
        
        for item in transcript_data['transcript']:
            time_in_minutes = item['start'] / 60
            time_group = int(time_in_minutes / 5)
            
            if time_group > current_time_group and current_paragraph:
                md_content.append(" ".join(current_paragraph))
                md_content.append("")
                current_paragraph = []
                current_time_group = time_group
            
            current_paragraph.append(item['text'])
        
        # 最後の段落を追加
        if current_paragraph:
            md_content.append(" ".join(current_paragraph))
        
        # 生成情報
        md_content.append("")
        md_content.append("---")
        md_content.append(f"文字起こし生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(md_content)

    def save_transcript_to_file(self, md_content, output_path, video_id):
        """
        文字起こしをファイルに保存
        
        Args:
            md_content (str): Markdown形式の文字起こし
            output_path (str): 出力ディレクトリのパス
            video_id (str): 動画ID
            
        Returns:
            str: 保存したファイルのパス
        """
        if not md_content:
            return None
        
        # 出力ディレクトリが存在しない場合は作成
        os.makedirs(output_path, exist_ok=True)
        
        # ファイル名を設定
        file_path = os.path.join(output_path, f"{video_id}.md")
        
        # ファイルに書き込み
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        return file_path

def process_video(video_url, output_dir, video_info=None):
    """
    動画の文字起こしを処理
    
    Args:
        video_url (str): YouTube動画のURL
        output_dir (str): 出力ディレクトリのパス
        video_info (dict, optional): 動画情報
        
    Returns:
        bool: 処理が成功したかどうか
    """
    transcriber = YouTubeTranscription()
    
    try:
        # 動画IDを取得
        video_id = transcriber.get_video_id_from_url(video_url)
        
        # 出力ファイルのパスを確認
        output_path = Path(output_dir)
        output_file = output_path / f"{video_id}.md"
        
        # すでに文字起こしが存在する場合はスキップ
        if output_file.exists():
            logger.info(f"動画ID {video_id} の文字起こしはすでに存在します。スキップします。")
            return False
        
        # 文字起こしを取得
        transcript_data = transcriber.get_transcript(video_id)
        
        if not transcript_data:
            logger.error(f"動画ID {video_id} の文字起こしを取得できませんでした")
            return False
        
        # Markdown形式にフォーマット
        md_content = transcriber.format_transcript_as_markdown(transcript_data, video_info)
        
        # ファイルに保存
        saved_path = transcriber.save_transcript_to_file(md_content, output_dir, video_id)
        
        if saved_path:
            logger.info(f"文字起こしを {saved_path} に保存しました")
            return True
        else:
            logger.error("文字起こしの保存に失敗しました")
            return False
    
    except Exception as e:
        logger.error(f"エラー: {e}")
        return False

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='YouTube動画の文字起こしを取得してMarkdownファイルに保存します')
    parser.add_argument('--livestreams-json', help='livestreams.jsonファイルのパス', required=True)
    parser.add_argument('--output-dir', help='出力ディレクトリのパス', required=True)
    parser.add_argument('--limit', help='処理する動画の数（デフォルト: 1）', type=int, default=1)
    
    args = parser.parse_args()
    
    try:
        # livestreams.jsonを読み込み
        with open(args.livestreams_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 動画リストを取得
        livestreams = data.get('livestreams', [])
        
        if not livestreams:
            logger.error("動画リストが空です")
            return 1
        
        logger.info(f"合計 {len(livestreams)} 件の動画が見つかりました")
        
        # 処理する動画の数を制限
        processed_count = 0
        
        for video in livestreams:
            if processed_count >= args.limit:
                break
            
            video_url = video.get('url')
            if not video_url:
                continue
            
            logger.info(f"処理中: {video.get('title', video_url)}")
            
            # 動画を処理
            success = process_video(video_url, args.output_dir, video)
            
            if success:
                processed_count += 1
                logger.info(f"処理完了: {processed_count}/{args.limit}")
            
            # APIレート制限を避けるために少し待機
            if processed_count < args.limit:
                time.sleep(2)
        
        logger.info(f"合計 {processed_count} 件の動画を処理しました")
        return 0
    
    except Exception as e:
        logger.error(f"エラー: {e}")
        return 1

if __name__ == '__main__':
    exit(main())
