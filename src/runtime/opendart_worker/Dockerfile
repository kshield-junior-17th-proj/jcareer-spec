FROM public.ecr.aws/lambda/python:3.12

COPY opendart_worker/requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY api/app ${LAMBDA_TASK_ROOT}/app
COPY opendart_worker/handler.py ${LAMBDA_TASK_ROOT}/handler.py

CMD ["handler.lambda_handler"]
