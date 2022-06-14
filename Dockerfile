FROM python:3.10

WORKDIR /src
EXPOSE 8080

RUN apt-get update
RUN apt-get remove mariadb-common -y
RUN apt-get install default-mysql-client libmariadb-dev -y
# necessary for profiler
RUN apt-get update && apt-get install -y curl perl-modules procps && rm -rf /var/lib/apt/lists/*

RUN pip install poetry==1.1.11
RUN poetry config virtualenvs.create false
COPY poetry.lock /src/
COPY pyproject.toml /src/
RUN poetry install

COPY . /src
RUN cd /src && python setup.py develop

RUN chmod +x /src/bin/run.sh
RUN cd /src/translations && sh compile.sh

CMD ["/src/bin/run.sh"]
