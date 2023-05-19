from typing import List
import base64
import httpx
from graia.ariadne.message.element import Image

from constants import config
from .base import DrawingAPI
from loguru import logger


def basic_auth_encode(authorization: str) -> str:
    authorization_bytes = authorization.encode('utf-8')
    encoded_authorization = base64.b64encode(authorization_bytes).decode('utf-8')
    return f"Basic {encoded_authorization}"


def init_authorization():
    if config.sdwebui.authorization != '':
        return basic_auth_encode(config.sdwebui.authorization)
    else:
        return ''


class SDWebUI(DrawingAPI):

    def __init__(self):
        self.headers = {
            "Authorization": f"{init_authorization()}"
        }

    async def text_to_img(self, prompt):
        logger.info("用户传入的提示词为：", prompt)
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
            response = await httpx.AsyncClient(timeout=config.sdwebui.timeout).post(f"{config.sdwebui.api_url}sdapi/v1/options",
                                                                                json=option_payload, headers=self.headers)
        else:
            option_payload = {
                "sd_model_checkpoint": "meinamix_v9.safetensors",
            }
            response = await httpx.AsyncClient(timeout=config.sdwebui.timeout).post(f"{config.sdwebui.api_url}sdapi/v1/options",
                                                                                    json=option_payload, headers=self.headers)

        resp = await httpx.AsyncClient(timeout=config.sdwebui.timeout).post(f"{config.sdwebui.api_url}sdapi/v1/txt2img",
                                                                            json=payload, headers=self.headers)
        resp.raise_for_status()
        r = resp.json()
        images = []
        for i in r['images']:
            images.append(Image(base64=i))
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
