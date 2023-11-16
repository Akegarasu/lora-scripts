FROM nvcr.io/nvidia/pytorch:23.07-py3

EXPOSE 28000

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && apt update && apt install python3-tk -y

RUN mkdir /app

WORKDIR /app
RUN git clone --recurse-submodules https://github.com/Akegarasu/lora-scripts

WORKDIR /app/lora-scripts
RUN pip install xformers==0.0.21 --no-deps && pip install -r requirements.txt

WORKDIR /app/lora-scripts/sd-scripts
RUN pip install -r requirements.txt

WORKDIR /app/lora-scripts

CMD ["python", "gui.py", "--listen"]