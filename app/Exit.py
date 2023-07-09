# -*- coding: UTF-8 -*-

class Exit():
    
    @staticmethod
    def msg(msg, detail):
        print(msg + " error: " + detail)
        exit(1)
    
    @staticmethod
    def exit(code):
        exit(code)
