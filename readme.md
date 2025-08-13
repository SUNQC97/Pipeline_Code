pip install -r requirements.txt


Problem:
1.这个Kanal_inputs 不应该作为state，因为很多时候，Virtuos和TwinCAT并不是一台电脑，不能共用一个state。这点需要修改一下

2.打开achse或者kanal的xml，读取item的index，这个可以合并成一个def

3.数据不同 # Definition of default axes group  这部分不太一样


4. Skip once的逻辑有问题 要处理一下


思路：
1.把xml文件结构和轴号以及对应的kanal的号  传入write_xml_to_new_kanal/axis，先根据kanal的号修改default。（因为创建轴node的时候，默认的都是kanal_1）


实现过程：
1.每创建一个新的node，就调用write_xml_to_new_kanal/axis

certificates:
winget install ShiningLight.OpenSSL.Light

in Powershell
openssl genrsa -out client_key.pem 2048
openssl req -x509 -days 365 -new -key client_key.pem -out client_cert.pem -config .\ssl_client.conf -extensions v3_req

openssl genrsa -out server_key.pem 2048
openssl req -x509 -days 365 -new -key server_key.pem -out server_cert.pem -config .\ssl_server.conf -extensions v3_req


openssl x509 -in server_cert.pem -outform der -out server_cert.der

