import tornado.web
from tornado import gen
from decouple import config

from ..celery.actions import ACTION_EVALUATE, queue_name
from ..celery.tasks import TASK_NLU_EVALUATE_UPDATE
from ..celery.app import celery_app
from .. import settings

from . import ApiHandler
from ..utils import ValidationError
from ..utils import authorization_required
from ..utils import AuthorizationIsRequired
from ..utils import NEXT_LANGS
from ..utils import backend


EVALUATE_STATUS_EVALUATED = 'evaluated'
EVALUATE_STATUS_FAILED = 'failed'


class EvaluateHandler(ApiHandler):
    @tornado.web.asynchronous
    @gen.engine
    @authorization_required
    def post(self):
        language = self.get_argument('language', default=None)

        if language and (
            language not in settings.SUPPORTED_LANGUAGES.keys() and
            language not in NEXT_LANGS.keys()
        ):
            raise ValidationError(
                'Language \'{}\' not supported by now.'.format(language),
                field='language')

        repository_authorization = self.repository_authorization()
        if not repository_authorization:
            raise AuthorizationIsRequired()

        update = backend().request_backend_parse('evaluate', repository_authorization, language)

        if not update.get('update'):
            raise ValidationError(
                'This repository has never been trained',
                field='language')

        try:
            evaluate_task = celery_app.send_task(
                TASK_NLU_EVALUATE_UPDATE,
                args=[
                    update.get('update_id'),
                    update.get('user_id'),
                    repository_authorization
                ],
                queue=queue_name(ACTION_EVALUATE, update.get('language')))
            evaluate_task.wait()
            evaluate = evaluate_task.result
            evaluate_report = {
                'language': language,
                'status': EVALUATE_STATUS_EVALUATED,
                'update_id': update.get('update_id'),
                'evaluate_id': evaluate.get('id'),
                'evaluate_version': evaluate.get('version'),
            }
        except Exception as e:
            from .. import logger
            logger.exception(e)

            evaluate_report = {
                'status': EVALUATE_STATUS_FAILED,
                'error': str(e),
            }

        self.finish(evaluate_report)
