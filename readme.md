pip install -r requirements.txt


Problem:
1.这个Kanal_inputs 不应该作为state，因为很多时候，Virtuos和TwinCAT并不是一台电脑，不能共用一个state。这点需要修改一下

2.打开achse或者kanal的xml，读取item的index，这个可以合并成一个def

