#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube過去配信取得ツール

指定されたYouTubeチャンネルの過去配信一覧を取得し、JSON形式で出力します。
"""

import os
import json
import argparse
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class YouTubeLivestreamExtractor:
    """YouTubeチャンネルの過去配信を取得するクラス"""

    def __init__(self, api_key):
        """
        初期化メソッド
        
        Args:
            api_key (str): YouTube Data API v3のAPIキー
        """
        self.youtube = build('youtube', 'v3', developerKey=api_key)
    
    def get_channel_id(self, channel_url):
        """
        チャンネルURLからチャンネルIDを取得
        
        Args:
            channel_url (str): YouTubeチャンネルのURL
            
        Returns:
            str: チャンネルID
        """
        # URLからチャンネル名を抽出
        if '/channel/' in channel_url:
            return channel_url.split('/channel/')[1].split('/')[0]
        elif '/c/' in channel_url or '/user/' in channel_url or '/@' in channel_url:
            # カスタムURLの場合はまずHTMLページを取得してチャンネルIDを探す
            import requests
            import re
            
            try:
                response = requests.get(channel_url)
                response.raise_for_status()
                
                # チャンネルIDを正規表現で検索
                channel_id_match = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"', response.text)
                if channel_id_match:
                    return channel_id_match.group(1)
                
                # 上記で見つからない場合はAPIで検索
                channel_name = ""
                if '/c/' in channel_url:
                    channel_name = channel_url.split('/c/')[-1].split('/')[0]
                elif '/user/' in channel_url:
                    channel_name = channel_url.split('/user/')[-1].split('/')[0]
                elif '/@' in channel_url:
                    channel_name = channel_url.split('/@')[-1].split('/')[0]
                
                if channel_name:
                    response = self.youtube.search().list(
                        part='snippet',
                        q=channel_name,
                        type='channel',
                        maxResults=5  # 複数の結果を取得して正確なものを探す
                    ).execute()
                    
                    # チャンネル名が完全一致するものを探す
                    for item in response.get('items', []):
                        if item['snippet']['title'].lower() == channel_name.lower() or \
                           channel_name.lower() in item['snippet']['title'].lower():
                            return item['id']['channelId']
                    
                    # 完全一致がなければ最初の結果を使用
                    if response.get('items'):
                        return response['items'][0]['id']['channelId']
                
                raise ValueError(f"チャンネル '{channel_url}' のIDが見つかりませんでした。")
            except Exception as e:
                print(f"エラー: {e}")
                return None
        else:
            raise ValueError("無効なチャンネルURLです。")
    
    def get_channel_info(self, channel_id):
        """
        チャンネル情報を取得
        
        Args:
            channel_id (str): チャンネルID
            
        Returns:
            dict: チャンネル情報
        """
        try:
            response = self.youtube.channels().list(
                part='snippet,statistics',
                id=channel_id
            ).execute()
            
            if response['items']:
                channel = response['items'][0]
                return {
                    'id': channel_id,
                    'title': channel['snippet']['title'],
                    'description': channel['snippet']['description'],
                    'publishedAt': channel['snippet']['publishedAt'],
                    'viewCount': channel['statistics']['viewCount'],
                    'subscriberCount': channel['statistics'].get('subscriberCount', 'hidden'),
                    'videoCount': channel['statistics']['videoCount']
                }
            else:
                raise ValueError(f"チャンネルID '{channel_id}' が見つかりませんでした。")
        except HttpError as e:
            print(f"エラー: {e}")
            return None
    
    def get_livestreams(self, channel_id, max_results=50):
        """
        チャンネルの過去配信一覧を取得
        
        Args:
            channel_id (str): チャンネルID
            max_results (int, optional): 取得する最大件数
            
        Returns:
            list: 過去配信のリスト
        """
        livestreams = []
        next_page_token = None
        
        try:
            # まずはチャンネルのアップロード動画プレイリストIDを取得
            channels_response = self.youtube.channels().list(
                part='contentDetails',
                id=channel_id
            ).execute()
            
            if not channels_response.get('items'):
                print(f"チャンネルID '{channel_id}' の情報が取得できませんでした。")
                return livestreams
            
            # アップロード動画プレイリストID
            uploads_playlist_id = channels_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            
            # チャンネルのすべてのアップロード動画を取得
            while True and len(livestreams) < max_results:
                playlist_items_response = self.youtube.playlistItems().list(
                    part='snippet,contentDetails',
                    playlistId=uploads_playlist_id,
                    maxResults=50,  # APIの最大値
                    pageToken=next_page_token
                ).execute()
                
                video_ids = [item['contentDetails']['videoId'] for item in playlist_items_response.get('items', [])]
                
                if video_ids:
                    # 動画の詳細情報を取得
                    videos_response = self.youtube.videos().list(
                        part='snippet,contentDetails,statistics,liveStreamingDetails',
                        id=','.join(video_ids)
                    ).execute()
                    
                    # ライブ配信のみをフィルタリング
                    for video in videos_response.get('items', []):
                        # liveStreamingDetailsがある、またはタイトルや説明に「配信」「生放送」「ライブ」などの文字が含まれる動画
                        is_livestream = False
                        
                        if 'liveStreamingDetails' in video:
                            is_livestream = True
                        elif ('snippet' in video and 
                              ('title' in video['snippet'] or 'description' in video['snippet'])):
                            title = video['snippet'].get('title', '').lower()
                            description = video['snippet'].get('description', '').lower()
                            livestream_keywords = ['配信', '生放送', 'ライブ', 'live', 'stream', '実況']
                            
                            for keyword in livestream_keywords:
                                if (keyword in title.lower() or keyword in description.lower()):
                                    is_livestream = True
                                    break
                        
                        if is_livestream:
                            livestream_data = {
                                'id': video['id'],
                                'title': video['snippet']['title'],
                                'description': video['snippet']['description'],
                                'publishedAt': video['snippet']['publishedAt'],
                                'channelId': video['snippet']['channelId'],
                                'channelTitle': video['snippet']['channelTitle'],
                                'thumbnails': video['snippet']['thumbnails'],
                                'duration': video['contentDetails']['duration'],
                                'viewCount': video['statistics'].get('viewCount', '0'),
                                'likeCount': video['statistics'].get('likeCount', '0'),
                                'commentCount': video['statistics'].get('commentCount', '0'),
                                'actualStartTime': video.get('liveStreamingDetails', {}).get('actualStartTime', None),
                                'actualEndTime': video.get('liveStreamingDetails', {}).get('actualEndTime', None),
                                'scheduledStartTime': video.get('liveStreamingDetails', {}).get('scheduledStartTime', None),
                                'concurrentViewers': video.get('liveStreamingDetails', {}).get('concurrentViewers', '0'),
                                'url': f"https://www.youtube.com/watch?v={video['id']}"
                            }
                            livestreams.append(livestream_data)
                
                next_page_token = playlist_items_response.get('nextPageToken')
                
                # 次のページがない場合は終了
                if not next_page_token:
                    break
            
            # 日付の新しい順にソート
            livestreams.sort(key=lambda x: x['publishedAt'], reverse=True)
            
            # 最大件数に制限
            return livestreams[:max_results]
        except Exception as e:
            print(f"エラー: {e}")
            return livestreams
    
    def get_all_data(self, channel_url, max_results=50):
        """
        チャンネル情報と過去配信一覧を取得
        
        Args:
            channel_url (str): YouTubeチャンネルのURL
            max_results (int, optional): 取得する最大件数
            
        Returns:
            dict: チャンネル情報と過去配信一覧
        """
        channel_id = self.get_channel_id(channel_url)
        if not channel_id:
            return None
        
        channel_info = self.get_channel_info(channel_id)
        if not channel_info:
            return None
        
        livestreams = self.get_livestreams(channel_id, max_results)
        
        return {
            'channel': channel_info,
            'livestreams': livestreams,
            'total': len(livestreams),
            'generated_at': datetime.now().isoformat()
        }


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='YouTubeチャンネルの過去配信一覧を取得します')
    parser.add_argument('channel_url', help='YouTubeチャンネルのURL')
    parser.add_argument('--api-key', help='YouTube Data API v3のAPIキー', default=os.environ.get('YOUTUBE_API_KEY'))
    parser.add_argument('--output', help='出力ファイル名', default='livestreams.json')
    parser.add_argument('--max-results', help='取得する最大件数', type=int, default=50)
    
    args = parser.parse_args()
    
    if not args.api_key:
        print("エラー: APIキーが指定されていません。--api-keyオプションまたはYOUTUBE_API_KEY環境変数で指定してください。")
        return 1
    
    extractor = YouTubeLivestreamExtractor(args.api_key)
    data = extractor.get_all_data(args.channel_url, args.max_results)
    
    if data:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"過去配信一覧を {args.output} に保存しました。")
        return 0
    else:
        print("データの取得に失敗しました。")
        return 1


if __name__ == '__main__':
    exit(main())
