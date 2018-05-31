# -*- coding:utf8 -*-
import sys
import socket
import hashlib
import threading
import datetime
import time
import struct
from base64 import b64encode, b64decode
from mtcnn.mtcnn import MTCNN
import redis
import numpy as np
import json
import cv2
import face_recognition
import logging
from logging.handlers import TimedRotatingFileHandler
# from config import HOST, WEBSOCKET_PORT

HOST = '172.28.50.66'
WEBSOCKET_PORT = 8020
pool = redis.ConnectionPool(host='172.28.50.91', port=6379, db=0, password=123456)
detector = MTCNN()
# 比检测位置向外扩一些
t = 2


def log(name, path):
    logFilePath = path
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    handler = TimedRotatingFileHandler(logFilePath,
                                       when="D",
                                       interval=1,
                                       backupCount=7)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger


detective_log = log('detective', r'/var/log/websocket/detective.log')
recognition_log = log('recognition', r'/var/log/websocket/recognition.log')

def load_redis():
    data = []
    r = redis.Redis(connection_pool=pool, decode_responses=True)

    pipe = r.pipeline()
    pipe_size = 100000

    lenght = 0
    key_list = []
    keys = r.hkeys('mobile_photo')
    for key in keys:
        key_list.append(key)
        pipe.hget('mobile_photo', key)
        if lenght < pipe_size:
            lenght += 1
        else:
            data.extend([json.loads(i) for i in pipe.execute()])
            lenght = 0
            key_list = []

    data.extend([json.loads(i) for i in pipe.execute()])
    return data


def bytes2ndarry(bes):
    return cv2.imdecode(np.frombuffer(bes, np.uint8), -1)

class WebSocket(threading.Thread):  # 继承Thread

    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self, conn, index, name, remote, path="/"):
        threading.Thread.__init__(self)  # 初始化父类Thread
        self.conn = conn
        self.index = index
        self.name = name
        self.remote = remote
        self.path = path
        self.buffer = bytes()
        self.handshaken()
        self.queue = []
        self.queue_tmp = []
        self.data = {}
        self.timer = None

    def handshaken(self):
        headers = {}
        flag = True
        while flag:
            self.buffer += self.conn.recv(1024)
            buffer_str = bytes.decode(self.buffer, encoding='utf-8')
            # print('buffer:', buffer_str)
            if buffer_str.find('\r\n\r\n') != -1:
                header, data = buffer_str.split('\r\n\r\n', 1)
                # print('header:', header)
                # print('data:', data)
                for line in header.split("\r\n")[1:]:
                    key, value = line.split(": ", 1)
                    headers[key] = value
                headers["Location"] = ("wss://%s%s" % (headers["Host"], self.path))
                key = headers['Sec-WebSocket-Key']
                token = b64encode(hashlib.sha1(str.encode(str(key + self.GUID))).digest())
                handshake = "HTTP/1.1 101 Switching Protocols\r\n" \
                            "Upgrade: websocket\r\n" \
                            "Connection: Upgrade\r\n" \
                            "Sec-WebSocket-Accept: " + bytes.decode(token) + "\r\n" \
                                                                             "WebSocket-Origin: " + str(
                    headers["Origin"]) + "\r\n" \
                                         "WebSocket-Location: " + str(headers["Location"]) + "\r\n\r\n"

                # print('send:', handshake)
                self.conn.send(str.encode(str(handshake)))
                print('Socket %s Handshaken with %s success!' % (self.index, self.remote))
                flag = False
                # sendMessage(u'Welcome, ' + self.name + ' !')
                # self.sendMessage('Welcome, ' + self.name + ' !')

    def run(self):  # 重载Thread的run
        print('Socket%s Start!' % self.index)
        t = threading.Timer(1, self.next_name)
        t.start()
        jsq = 0
        buffer = bytes()
        while True:
            msg = ''
            mm = self.conn.recv(1024 * 1000000)

            # print(type(mm))
            if len(mm) <= 0:
                if buffer:
                    msg = self.parse_data(buffer)
                    buffer = ''
                else:
                    continue
            else:
                # 报文头
                if mm[0] == 129:
                    if buffer:
                        msg = self.parse_data(buffer)
                    buffer = mm
                else:
                    buffer += mm
            # print(msg)
            # print(len(msg))
            if msg:
                # print(type(msg))
                # print(msg[23:])
                # print(jsq)
                info = b64decode(msg[23:])
                # print(type(info))
                # print(info)
                resulte = self.face_handle(bytes2ndarry(info))
                resulte_str = json.dumps(resulte)
                if msg == 'quit':
                    self.timer.cancel()
                    self.conn.close()
                    break  # 退出线程
                else:
                    # print('##########################', jsq, '##')
                    jsq += 1
                    self.sendMessage(resulte_str)
                    # a = [{'name': 'zyb'}]
                    # self.sendMessage(json.dumps(a))

    def face_handle(self, img):
        res_list = []
        redis_data = load_redis()
        face_encodings_knows = [np.array(json.loads(i['feature'])) for i in redis_data]
        start = time.time()
        faceRects = detector.detect_faces(img)
        end = time.time()
        flag = True
        log_data = {'createtime': int(time.time()*1000),
                    'app': '轻行智眼系统',
                    'alg': '思源云人脸检测算法',
                    'interval': int((end-start) *1000),
                    'result': 1 if len(faceRects) > 0 else 0
                    }

        detective_log.info('|'.join([str(k) + '=' + str(v) for k, v in log_data.items()]))
        if len(faceRects) > 0:  # 大于0则检测到人脸
            for idx, faceRect in enumerate(faceRects):  # 单独框出每一张人脸
                x, y, w, h = faceRect['box']
                data = {
                    'x': x,
                    'y': y,
                    'w': w,
                    'h': h,
                }
                start = time.time()
                face_encoding = face_recognition.face_encodings(img[y - t: y + h + t, x - t: x + w + t])
                end = time.time()
                if len(face_encoding) != 0:
                    face_encoding = face_encoding[0]
                    face_res = face_recognition.face_distance(face_encodings_knows, face_encoding)
                    k = face_res.min()
                    f = face_res.argmin()
                    data['recognition'] = '-1'
                    print('score:', k)
                    # print('end:', end)
                    # print('start:', start)
                    data['score'] = k
                    data['interval'] =int((end - start) * 1000)
                    if 0 <= k < 0.13:
                        data['syScore'] = 1
                    else:
                        data['syScore'] = -1.0835 * k + 1.1346
                    if k < 0.45:
                        data['result'] = 1
                        data_tmp = redis_data[f]
                        if data_tmp not in self.queue and data_tmp not in self.queue_tmp:
                            self.queue.append(data_tmp)
                        if not self.data:
                            self.data = data_tmp
                        if data_tmp == self.data and flag:
                            # data.update(self.setData())
                            data['recognition'] = '1'
                            flag = False
                        else:
                            data['recognition'] = '0'
                    else:
                        data['result'] = 0
                        # data.update(self.setData())

                    data.update(self.setData())
                    res_list.append(data)
                    data['createTime'] = int(time.time()*1000)
                    data['userType'] = 1
                    data['company'] = 2
                    recognition_log.info('|'.join([str(k) + '=' + str(v) for k, v in data.items()]))
                    break

        # 如果被叫到的下一个人不在当前图像内
        if flag and self.data:
            data = {'x': 0, 'y': 0, 'w': 0, 'h': 0}
            data.update(self.setData())
            res_list.append(data)

        return res_list

    def setData(self):
        data = {}
        what_time = self.now_time()
        data['userType'] = self.data.get('userType')
        data['name'] = self.data.get('name')
        data['company'] = self.data.get('company')
        data['position'] = self.data.get('position')
        data['iName'] = self.data.get('iName')
        data['iCompany'] = self.data.get('iCompany')
        data['iPosition'] = self.data.get('iPosition')
        data['visitTime'] = self.data.get('visitTime')
        data['mp3'] = self.data.get(what_time[0])
        data['img'] = self.data.get('cloudUrl')
        if self.data.get('sex'):
            sex = '女士' if self.data['sex'] == 0 else '先生'
            data['msg'] = data['name'] + sex + ', ' + what_time[1]
        return data

    def next_name(self):
        if len(self.queue) != 0:
            self.data = self.queue[0]
            self.queue = self.queue[1:]
            self.queue_tmp.append(self.data)
            del_timer = threading.Timer(10, self.del_tmp)
            del_timer.start()
        self.timer = threading.Timer(2, self.next_name)
        self.timer.start()

    def del_tmp(self):
        self.queue_tmp = self.queue_tmp[1:]

    def now_time(self):
        now_hour = datetime.datetime.now().hour
        if 5 <= now_hour < 11:
            return 'morning', '早上好'
        elif 11 <= now_hour < 14:
            return 'noon', '中午好'
        elif 14 <= now_hour < 19:
            return 'afternoon', '下午好'
        elif 19 <= now_hour or now_hour < 5:
            return 'evening', '晚上好'

    def parse_data(self, data):
        v = data[1] & 0x7f
        if v == 0x7e:
            p = 4
        elif v == 0x7f:
            p = 10
        else:
            p = 2
        mask = data[p: p + 4]
        data = data[p + 4:]
        i = 0
        raw_str = ""
        for d in data:
            raw_str += chr(d ^ mask[i % 4])
            i += 1
        return raw_str

    def sendMessage(self, message):
        msgLen = len(message)
        backMsgList = [struct.pack('B', 129)]

        if msgLen <= 125:
            backMsgList.append(struct.pack('b', msgLen))
        elif msgLen <= 65535:
            backMsgList.append(struct.pack('b', 126))
            backMsgList.append(struct.pack('>h', msgLen))
        elif msgLen <= (2 ^ 64 - 1):
            backMsgList.append(struct.pack('b', 127))
            backMsgList.append(struct.pack('>h', msgLen))
        else:
            print("the message is too long to send in a time")
            return
        message_byte = bytes()
        # print(type(backMsgList[0]))
        for c in backMsgList:
            message_byte += c
        message_byte += bytes(message, encoding="utf8")
        self.conn.send(message_byte)


class WebSocketServer(object):
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = None

    def begin(self):
        print('WebSocketServer Start!')
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(50)

        i = 0
        while True:
            connection, address = self.socket.accept()

            username = address[0]
            newSocket = WebSocket(connection, i, username, address)
            newSocket.start()  # 开始线程,执行run函数
            i = i + 1


if __name__ == "__main__":
    server = WebSocketServer(HOST, int(sys.argv[1]))
    server.begin()
