import hashlib
import re
from typing import List, Any
import base64
import httpx
from graia.ariadne.message.element import Image

from constants import config
from .base import DrawingAPI
import aiohttp
import ctypes
from graia.ariadne.message.element import Image as GraiaImage
import asyncio
hashu = lambda word: ctypes.c_uint64(hash(word)).value


def basic_auth_encode(authorization: str) -> str:
    authorization_bytes = authorization.encode('utf-8')
    encoded_authorization = base64.b64encode(authorization_bytes).decode('utf-8')
    return f"Basic {encoded_authorization}"


def init_authorization():
    if config.sdwebui.authorization != '':
        return basic_auth_encode(config.sdwebui.authorization)
    else:
        return ''


# analyzing parameters by imitating mj
def parse_args(args_str, default=None):
    arg_dict = {}
    arg_name = None
    arg_values = []
    if args_str != "":
        for arg in args_str.split():
            if arg.startswith("--"):
                if arg_name is not None:
                    if len(arg_values) == 1:
                        arg_dict[arg_name] = arg_values[0]
                    elif len(arg_values) > 1:
                        arg_dict[arg_name] = arg_values[0:]
                    else:
                        arg_dict[arg_name] = default
                arg_name = arg.lstrip("-")
                arg_values = []
            else:
                arg_values.append(arg)

        if arg_name is not None:
            if len(arg_values) == 1:
                arg_dict[arg_name] = arg_values[0]
            elif len(arg_values) > 1:
                arg_dict[arg_name] = arg_values[0:]
            else:
                arg_dict[arg_name] = default

    return arg_dict

    # deal with args


def deal_with_args(parsed_args):
    # deal with args
    width = 512
    height = 512
    pm = False
    if bool(parsed_args):
        if 'ar' in parsed_args:
            ar_value = parsed_args.get('ar')
            if ar_value == '1:1':
                width = 512
                height = 512
            if ar_value == '3:4':
                width = 768
                height = 1024
            if ar_value == '4:3':
                width = 1024
                height = 768
            if ar_value == '9:16':
                width = 576
                height = 1024
            if ar_value == '16:9':
                width = 1024
                height = 576
        if 'pm' in parsed_args:
            pm = True

    return width, height, pm


async def download_image(url) -> GraiaImage:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return GraiaImage(data_bytes=await resp.read())


class SDWebUI(DrawingAPI):

    def __init__(self):
        self.baidu_api_key = None
        self.deepl_api_key = None
        self.baidu_secret_key = None
        self.client = httpx.AsyncClient()
        self.headers = {
            "Authorization": f"{init_authorization()}"
        }

    async def text_to_img(self, prompt):
        if '--L' not in prompt:
            payload = {
                'enable_hr': 'false',
                'denoising_strength': 0.45,
                'prompt': f'{config.sdwebui.prompt_prefix}, {prompt}',
                'steps': 15,
                'seed': -1,
                'batch_size': 1,
                'n_iter': 1,
                'cfg_scale': 7.5,
                'restore_faces': 'false',
                'tiling': 'false',
                'script_name': f'{config.sdwebui.script_name}',
                'script_args': [f'{prompt}'],
                'negative_prompt': config.sdwebui.negative_prompt,
                'eta': 0,
                'sampler_name': config.sdwebui.sampler_index
            }

            for key, value in config.sdwebui.dict(exclude_none=True).items():
                if isinstance(value, bool):
                    payload[key] = 'true' if value else 'false'
                else:
                    payload[key] = value

            if '--real-c' in prompt:
                option_payload = {
                    "sd_model_checkpoint": "chilloutmix.safetensors",
                }
                response = await httpx.AsyncClient(timeout=config.sdwebui.timeout).post(
                    f"{config.sdwebui.api_url}sdapi/v1/options",
                    json=option_payload, headers=self.headers)
            else:
                option_payload = {
                    "sd_model_checkpoint": "meinamix_v9.safetensors",
                }
                response = await httpx.AsyncClient(timeout=config.sdwebui.timeout).post(
                    f"{config.sdwebui.api_url}sdapi/v1/options",
                    json=option_payload, headers=self.headers)

            resp = await httpx.AsyncClient(timeout=config.sdwebui.timeout).post(
                f"{config.sdwebui.api_url}sdapi/v1/txt2img",
                json=payload, headers=self.headers)
            resp.raise_for_status()
            r = resp.json()
            return [Image(base64=i) for i in r.get('images', [])]
        else:
            model_id = "d2fb9cf9-7999-4ae5-8bfe-f0df2d32abf8"
            # 更适合肖像的模型
            if '--R' in prompt:
                model_id = "a097c2df-8f0c-4029-ae0f-8fd349055e61"
            # need to remove
            pattern_list = ['nsfw', 'sex', 'naked', 'breast', 'sexual intercourse', 'nipple', 'pornographic', 'pussy',
                            '性', '性交', '裸体', '胸部', '色情', '乳头', '阴部']
            pattern = '|'.join(pattern_list)
            parsed_args = {}
            scene = prompt
            image_number = 1
            width = 512
            height = 512
            pm = False
            if scene != "":
                parsed_args = parse_args(scene)
                width_p, height_p, pm_p = deal_with_args(parsed_args)
                width = width_p
                height = height_p
                pm = pm_p
                index = scene.find("--")
                if index != -1:
                    scene = scene[:index]
            if bool(parsed_args):
                if 'pics' in parsed_args:
                    image_number = int(parsed_args.get('pics'))
            url = "https://cloud.leonardo.ai/api/rest/v1/generations"
            headers_post = {
                "accept": "application/json",
                "content-type": "application/json",
                "authorization": "Bearer f9104f8f-7083-4c1b-9acf-39011244092f"
            }
            headers_get = {
                "accept": "application/json",
                "authorization": "Bearer f9104f8f-7083-4c1b-9acf-39011244092f"
            }
            # 翻译用户提问为英文
            translated_prompt = await self.translate_with_deepl(scene, "zh", "en")
            if translated_prompt is None:
                translated_prompt = await self.translate_with_baidu(scene, "zh", "en")
            if translated_prompt is None:
                translated_prompt = scene
            translated_prompt = re.sub(pattern, '', translated_prompt)
            if "--real" in prompt:
                translated_prompt = translated_prompt + ", (realistic, photo-realistic:1.37)"
            payload = {
                "prompt": f"{translated_prompt}, {config.sdwebui.prompt_prefix}",
                "modelId": model_id,
                "width": width,
                "height": height,
                "promptMagic": True if pm else False,
                "public": False,
                "num_images": image_number,
                "presetStyle": "LEONARDO",
                "negative_prompt": "(nsfw:1.5),worst quality, bad quality, normal quality, cropping, out of focus, "
                                   "bad anatomy,"
                                   " sketch, lowres, deformed guitar, extra hand, extra guitar, extra digit, "
                                   "fewer digits, jpeg artifacts, signature, watermark, username, artist name"
            }
            print("莱奥纳多的入参是：", f"{payload}")
            response = await httpx.AsyncClient(timeout=config.sdwebui.timeout).post(url, json=payload,
                                                                                    headers=headers_post)
            print("莱奥纳多的返回值是：", f"{response.json()}")
            rj = response.json()
            pic_urls = []
            images = []
            if response.status_code == 200:
                generation_id = rj['sdGenerationJob']['generationId']
                print("获取到的创建ID是：", f"{generation_id}")
                url = url + f"/{generation_id}"
                while True:
                    resp = await httpx.AsyncClient(timeout=config.sdwebui.timeout).get(url, headers=headers_get)
                    rj = resp.json()
                    print("获取到的图片信息是：", f"{rj}")
                    if resp.status_code == 200:
                        if rj['generations_by_pk']['status'] == 'COMPLETE':
                            images = rj['generations_by_pk']['generated_images']
                            for image in images:
                                # if not image['nsfw']: 这里限制好像太强了
                                print("图片地址是：", image['url'])
                                pic_urls.append(image['url'])
                            break
                        else:
                            await asyncio.sleep(10)
            else:
                response.raise_for_status()

            for pic_url in pic_urls:
                image = await download_image(pic_url)
                images.append(image)
            return images

    async def img_to_img(self, init_images: List[Image], prompt=''):
        payload = {
            'init_images': [x.base64 for x in init_images],
            'enable_hr': 'false',
            'denoising_strength': 0.45,
            'prompt': f'{config.sdwebui.prompt_prefix}, {prompt}',
            'steps': 15,
            'seed': -1,
            'batch_size': 1,
            'n_iter': 1,
            'cfg_scale': 7.5,
            'restore_faces': 'false',
            'tiling': 'false',
            'script_name': f'{config.sdwebui.script_name}',
            'script_args': [f'{prompt}'],
            'negative_prompt': config.sdwebui.negative_prompt,
            'eta': 0,
            'sampler_index': config.sdwebui.sampler_index,
            "filter_nsfw": 'true' if config.sdwebui.filter_nsfw else 'false',
        }

        for key, value in config.sdwebui.dict(exclude_none=True).items():
            if isinstance(value, bool):
                payload[key] = 'true' if value else 'false'
            else:
                payload[key] = value

        resp = await httpx.AsyncClient(timeout=config.sdwebui.timeout).post(f"{config.sdwebui.api_url}sdapi/v1/img2img",
                                                                            json=payload, headers=self.headers)
        resp.raise_for_status()
        r = resp.json()
        return [Image(base64=i) for i in r.get('images', [])]

    async def translate_with_baidu(self, text: str, from_lang: str, to_lang: str) -> Any | None:
        url = "http://api.fanyi.baidu.com/api/trans/vip/translate"
        salt = str(hashu(text))
        self.baidu_api_key = '20230227001577503'
        self.baidu_secret_key = 'o9kxQADPCdFf56FHPCIv'
        sign_str = self.baidu_api_key + text + salt + self.baidu_secret_key  # don't forget to add the secret key
        sign = hashlib.md5(sign_str.encode()).hexdigest()
        params = {
            "q": text,
            "from": from_lang,
            "to": to_lang,
            "appid": self.baidu_api_key,
            "salt": salt,
            "sign": sign,
        }
        response = await self.client.get(url, params=params)
        if response.status_code != 200:
            return None
        return response.json()['trans_result'][0]['dst']

    async def translate_with_deepl(self, text: str, from_lang: str, to_lang: str) -> Any | None:
        url = "https://api-free.deepl.com/v2/translate"
        self.deepl_api_key = '1e23ad70-40b4-7e97-4d08-2239d2e114a6:fx'
        headers = {"Authorization": "DeepL-Auth-Key " + self.deepl_api_key}
        data = {
            "text": text,
            "source_lang": from_lang,
            "target_lang": to_lang,
        }
        response = await self.client.post(url, headers=headers, data=data)
        if response.status_code != 200:
            return None
        return response.json()['translations'][0]['text']
