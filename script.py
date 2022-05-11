"""
@ProjectName: DXY-2019-nCoV-Crawler
@FileName: script.py
@Author: Jiabao Lin
@Date: 2020/1/31
"""
from git import Repo
from pymongo import MongoClient
import os
import json
import time
import logging
import datetime
import requests
import pandas as pd


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

uri = '**Confidential**'
client = MongoClient(uri)
db = client['2019-nCoV']

collections = {
    'DXYOverall': 'overall',
    'DXYArea': 'area',
    'DXYNews': 'news',
    'DXYRumors': 'rumors'
}
time_types = ('pubDate', 'createTime', 'modifyTime', 'dataInfoTime', 'crawlTime', 'updateTime')


def dict_parser(document, city_dict=None):
    result = {}

    try:
        result['continentName'] = document['continentName']
        result['continentEnglishName'] = document['continentEnglishName']
    except KeyError:
        result['continentName'] = None
        result['continentEnglishName'] = None

    result['countryName'] = document['countryName']

    try:
        result['countryEnglishName'] = document['countryEnglishName']
    except KeyError:
        result['countryEnglishName'] = None

    result['provinceName'] = document['provinceName']
    result['provinceEnglishName'] = document.get('provinceEnglishName')
    result['province_zipCode'] = document.get('locationId')
    result['province_confirmedCount'] = document['confirmedCount']
    result['province_suspectedCount'] = document['suspectedCount']
    result['province_curedCount'] = document['curedCount']
    result['province_deadCount'] = document['deadCount']

    if city_dict:
        result['cityName'] = city_dict['cityName']
        result['cityEnglishName'] = city_dict.get('cityEnglishName')
        result['city_zipCode'] = city_dict.get('locationId')
        result['city_confirmedCount'] = city_dict['confirmedCount']
        result['city_suspectedCount'] = city_dict['suspectedCount']
        result['city_curedCount'] = city_dict['curedCount']
        result['city_deadCount'] = city_dict['deadCount']

    result['updateTime'] = datetime.datetime.fromtimestamp(int(document['updateTime']/1000))

    return result


def git_manager(changed_files):
    repo = Repo(path=os.path.split(os.path.realpath(__file__))[0])
    repo.index.add(changed_files)
    repo.index.commit(message='{datetime} - Change detected!'.format(datetime=datetime.datetime.now()))
    origin = repo.remote('origin')
    origin.push()
    logger.info('Pushing to GitHub successfully!')


class DB:
    def __init__(self):
        self.db = db

    def count(self, collection):
        return self.db[collection].count_documents(filter={})

    def dump(self, collection):
        return self.db[collection].aggregate(
            pipeline=[
                {
                    '$sort': {
                        'updateTime': -1,
                        'crawlTime': -1
                    }
                }
            ],
            allowDiskUse=True
        )


class Listener:
    def __init__(self):
        self.db = DB()

    def run(self):
        while True:
            self.listener()
            time.sleep(3600)

    def listener(self):
        changed_files = []
        for collection in collections:
            with open(
                os.path.join(
                    os.path.split(os.path.realpath(__file__))[0], 'json', collection + '.json'),
                'r', encoding='utf-8'
            ) as json_file:
                try:
                    static_data = json.load(json_file)
                except (UnicodeDecodeError, FileNotFoundError, json.decoder.JSONDecodeError):
                    static_data = None
            while True:
                request = requests.get(url='https://lab.isaaclin.cn/nCoV/api/' + collections.get(collection))
                if request.status_code == 200:
                    current_data = request.json()
                    break
                else:
                    time.sleep(1)
                    continue
            if static_data != current_data:
                self.json_dumper(collection=collection, content=current_data)
                changed_files.append('json/' + collection + '.json')
                cursor = self.db.dump(collection=collection)
                self.csv_dumper(collection=collection, cursor=cursor)
                changed_files.append('csv/' + collection + '.csv')
                cursor = self.db.dump(collection=collection)
                self.db_dumper(collection=collection, cursor=cursor)
                changed_files.append('json/' + collection + '-TimeSeries.json')
            logger.info('{collection} checked!'.format(collection=collection))
        if changed_files:
            git_manager(changed_files=changed_files)

    def json_dumper(self, collection, content=None):
        with open(
            os.path.join(
                os.path.split(
                    os.path.realpath(__file__))[0], 'json', collection + '.json'
            ),
            'w', encoding='utf-8'
        ) as json_file:
            json.dump(content, json_file, ensure_ascii=False, indent=4)

    def csv_dumper(self, collection, cursor):
        if collection == 'DXYArea':
            structured_results = []
            for document in cursor:
                if document.get('cities', None):
                    for city_counter in range(len(document['cities'])):
                        city_dict = document['cities'][city_counter]
                        structured_results.append(dict_parser(document=document, city_dict=city_dict))
                else:
                    structured_results.append(dict_parser(document=document))

            df = pd.DataFrame(structured_results)
            df.to_csv(
                path_or_buf=os.path.join(
                    os.path.split(os.path.realpath(__file__))[0], 'csv', collection + '.csv'),
                index=False, encoding='utf_8_sig', float_format="%i"
            )
        else:
            df = pd.DataFrame(data=cursor)
            for time_type in time_types:
                if time_type in df.columns:
                    df[time_type] = df[time_type].apply(
                        lambda x: ''
                        if pd.isna(x)
                        else datetime.datetime.fromtimestamp(x / 1000)
                    )

            df.to_csv(
                path_or_buf=os.path.join(
                    os.path.split(os.path.realpath(__file__))[0], 'csv', collection + '.csv'),
                index=False, encoding='utf_8_sig', date_format="%Y-%m-%d %H:%M:%S"
            )

    def db_dumper(self, collection, cursor):
        data = []
        for document in cursor:
            document.pop('_id')
            data.append(document)

        with open(
            os.path.join(
                os.path.split(
                    os.path.realpath(__file__))[0], 'json', collection + '-TimeSeries.json'
            ),
            'w', encoding='utf-8'
        ) as json_file:
            json.dump(data, json_file, ensure_ascii=False, indent=4)


if __name__ == '__main__':
    listener = Listener()
    listener.run()
