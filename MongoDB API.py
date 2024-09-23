from flask import Flask, request, json, Response
from pymongo import MongoClient, collection
import logging as log
import json
from cassandra.cluster import Cluster
from neo4j import GraphDatabase, RoutingControl


app = Flask(__name__)

class CassandraAPI:
    def __init__(self):
        cluster = Cluster(['cassandra1'])
        self.session = cluster.connect()

    def read(self, data):
        if 'Filter' in str(data):
            filt = data['Filter']
            result = self.session.execute("SELECT date FROM games.data WHERE ID = %s", [filt["ID"]])
        else:
            result = self.session.execute("SELECT date FROM games.data")
        return result

    def write(self, data):
        new_document = data['Document']
        self.session.execute("""
            INSERT INTO games.data (ID, date)
            VALUES (%s, %s)
        """, [new_document["ID"], new_document["date"]])

    def update(self, data):
        ID = data["Filter"]
        updated_data = data["DataToBeUpdated"]
        self.session.execute("""
            UPDATE games.data SET date = %s WHERE ID = %s;
        """, [updated_data["date"], ID["ID"]])

    def delete(self, data):
        deleted_data = data["Filter"]
        self.session.execute("""
            DELETE FROM games.data WHERE ID = %s;
        """, [deleted_data["ID"]])

class Neo4jAPI:
    def __init__(self):
       self.driver = GraphDatabase.driver("neo4j://gaming-neo4j_server1-1", auth=("neo4j", 'pass1234321'), database="neo4j")#"neo4j://localhost:7475", auth=("neo4j", 'pass1234321')
       self.driver.verify_connectivity()
       self.database = "neo4j"

    def read(self, data):
        if 'Filter' in str(data):
            data_to_find = data["Filter"]
            records, _, _ = self.driver.execute_query(
                "MATCH (a:games {ID: $ID})-[:dev]->(b:developers), (a:games {ID: $ID})-[:pub]->(c:publisher), (a:games {ID: $ID})-[:gen]->(d:genre), (a:games {ID: $ID})-[:lan]->(e:language) RETURN a.ID as ID, b.developers as dev, c.publisher as pub, d.genre as gen, e.language as lan",
                ID=data_to_find["ID"],
                database=self.database,
                routing_=RoutingControl.READ
            )
            return records
        else:
            records, _, _ = self.driver.execute_query(
                "MATCH (a:games)-[:dev]->(b:developers), (a:games)-[:pub]->(c:publisher), (a:games)-[:gen]->(d:genre), (a:games)-[:lan]->(e:language) RETURN a.ID as ID, b.developers as dev, c.publisher as pub, d.genre as gen, e.language as lan",
                database=self.database,
                routing_=RoutingControl.READ
            )
            return records

    def write(self, data):
        new_document = data["Document"]
        self.driver.execute_query(
            "MERGE (a:games {ID: $ID}) with a MATCH (c:developers {developers: $developers}), (d:publisher {publisher: $publisher}), (e:genre {genre: $genre}), (b:language {language: $language}) MERGE (a)-[:pub]->(d) MERGE (a)-[:lan]->(b) MERGE (a)-[:gen]->(e) MERGE (a)-[:dev]->(c)",
            routing_=RoutingControl.WRITE,
            ID=new_document["ID"],
            language=new_document["language"],
            developers=new_document["developers"],
            publisher=new_document["publisher"],
            genre=new_document["genre"],
            database=self.database
        )
        output = {'Status': 'Successfully Inserted'}
        return output

    def update(self, data):
        filt = data['Filter']
        data_to_update = data["DataToBeUpdated"]
        self.driver.execute_query("MATCH(:games {ID: $ID})-[r]->() DETACH DELETE r",
                                  ID = filt["ID"],
        )
        self.driver.execute_query("MATCH (a: games {ID: $ID})MATCH (c:developers {developers: $developers})MATCH (d:publisher {publisher: $publisher})MATCH (e:genre {genre: $genre})MATCH (b:language {language: $language}) MERGE (a)-[:pub]->(d)MERGE (a)-[:lan]->(b)MERGE (a)-[:gen]->(e)MERGE (a)-[:dev]->(c)",
                                  routing_=RoutingControl.WRITE, ID=filt["ID"],
                                  language=data_to_update["language"],
                                  developers=data_to_update["developers"],
                                  publisher=data_to_update["publisher"],
                                  genre=data_to_update["genre"],
                                  database=self.database
        )
    def delete(self, data):
        data_to_delete = data["Filter"]
        self.driver.execute_query("MATCH(p: games {ID: $ID}) DETACH DELETE p",
                                  ID = data_to_delete["ID"],
                                  database=self.database
        )

class MongoAPI:
    def __init__(self, data):
        log.basicConfig(level=log.DEBUG, format='%(asctime)s %(levelname)s:\n%(message)s\n')
        self.client = MongoClient('mongodb://mongodb1:27017/?replicaSet=rs0')

        database = data['database']
        collection = data['collection']
        cursor = self.client[database]
        self.collection = cursor[collection]
        self.data = data

    def read(self):
        log.info('Reading All Data')
        if 'Filter' in str(self.data):
            filt = self.data['Filter']
            documents = self.collection.find(filt)
        else:
            documents = self.collection.find()
        if 'count' in str(self.data):
            output = documents.count()
        else:
            output = [{item: data[item] for item in data if item != '_id'} for data in documents]
        return output

    def write(self, data):
        log.info('Writing Data')
        new_document = data['Document']
        response = self.collection.insert_one({"ID" : new_document["ID"], "name" : new_document["name"]})
        output = {'Status': 'Successfully Inserted',
                  'Document_ID': str(response.inserted_id)}
        return output

    def update(self):
        log.info('Updating Data')
        filt = self.data['Filter']
        updated_data = {"$set": {"name" : self.data['DataToBeUpdated']["name"]}}
        response = self.collection.update_many(filt, updated_data)
        output = {'Status': 'Successfully Updated' if response.modified_count > 0 else "Nothing was updated."}
        return output

    def delete(self, data):
        log.info('Deleting Data')
        filt = data['Filter']
        response = self.collection.delete_many(filt)
        output = {'Status': 'Successfully Deleted' if response.deleted_count > 0 else "Document not found."}
        return output

@app.route('/')
def base():
    return Response(response=json.dumps({"Status": "UP"}),
                    status=200,
                    mimetype='application/json')


@app.route('/mongodb', methods=['GET'])
def mongo_read():
    data = request.json  # Getting query in json format
    if data is None or data == {}:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')
    obj1 = MongoAPI(data)
    obj2 = CassandraAPI()
    obj3 = Neo4jAPI()
    responseCas = obj2.read(data)
    responseMong = obj1.read()
    responseNeo = obj3.read(data)
    for i in range(len(responseNeo)):
        responseMong[i]["date"] = responseCas[i]
        responseMong[i]["developers"] = responseNeo[i][1]
        responseMong[i]["publisher"] = responseNeo[i][2]
        responseMong[i]["language"] = responseNeo[i][4]
        responseMong[i]["genre"] = responseNeo[i][3]
    return Response(response=json.dumps(responseMong),
                    status=200,
                    mimetype='application/json')

@app.route('/mongodb', methods=['POST'])
def mongo_write():
    data = request.json
    if data is None or data == {} or 'Document' not in data:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')
    obj1 = MongoAPI(data)
    obj2 = CassandraAPI()
    obj3 = Neo4jAPI()
    obj2.write(data)
    obj3.write(data)
    response = obj1.write(data)
    return Response(response=json.dumps(response),
                    status=200,
                    mimetype='application/json')

@app.route('/mongodb', methods=['PUT'])
def mongo_update():
    data = request.json
    if data is None or data == {} or 'Filter' not in data:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')
    obj1 = MongoAPI(data)
    obj2 = CassandraAPI()
    obj3 = Neo4jAPI()
    obj2.update(data)
    obj3.update(data)
    response = obj1.update()
    return Response(response=json.dumps(response),
                    status=200,
                    mimetype='application/json')

@app.route('/mongodb', methods=['DELETE'])
def mongo_delete():
    data = request.json
    if data is None or data == {} or 'Filter' not in data:
        return Response(response=json.dumps({"Error": "Please provide connection information"}),
                        status=400,
                        mimetype='application/json')
    obj1 = MongoAPI(data)
    obj2 = CassandraAPI()
    obj3 = Neo4jAPI()
    obj2.delete(data)
    obj3.delete(data)
    response = obj1.delete(data)
    return Response(response=json.dumps(response),
                    status=200,
                    mimetype='application/json')


if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')