# -*- coding: utf-8 -*-
import requests
from flask import Flask, jsonify

from config import HOST, FLASK_PORT


app = Flask(__name__)


@app.route('/recognition/weather', methods=['GET', 'POST'])
def weather():
    result = {
        'status': 'success',
    }
    headers = {'content-type': 'application/json; charset=utf-8','Authorization': 'YXBpOjhmNTM4NGIzOTYxODQ3NzY5ZjQwMDJlMDI3MDA0YWE2'}

    r = requests.get(url='http://restapi.amap.com/v3/weather/weatherInfo?city=110000&key=b186680c4b0d8c42ffc5dc7431b1394f&extensions=all', headers=headers)
    if r.status_code == 200:
        t = r.text
        a = eval(t)

        l = []
        for i in a['forecasts'][0]['casts']:
            dic = {}
            day = i['date'].split('-')
            if day[1][:1] == '0':
                dic['date'] = day[1][1:] + '月' + day[2] + '日'
            else:
                dic['date'] = day[1] + '月' + day[2] + '日'

            dic['temp'] = min(i['nighttemp'], i['daytemp']) + '-' + max(i['daytemp'], i['nighttemp']) + '°'
            if i['dayweather'] == i['nightweather']:
                dic['weather'] = i['dayweather']
            else:
                dic['weather'] = i['dayweather'] + '转' + i['nightweather']
            l.append(dic)
        result['data'] = l
    else:
        result['status'] = 'error'

    return jsonify(result)


if __name__ == '__main__':
    app.run(host=HOST, debug=True, port=FLASK_PORT)
