FROM mongo:3.6.4             

FROM python:3

#Changing working directory
WORKDIR /app

#Coping requirements file to Docker Directory
COPY /requirements.txt /app

#Installing reuqired dependencies
RUN pip install --no-cache-dir -r requirements.txt

#Exposing the default ports
EXPOSE 7474
EXPOSE 7475
EXPOSE 7476

#Coping everything in the same forlder to Docker Directory
COPY ["MongoDB API.py", "/app"]
COPY . .

#Executing MongoDB API.py with python3выв
CMD ["python3","MongoDB API.py"]