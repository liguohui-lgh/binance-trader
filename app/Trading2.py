# -*- coding: UTF-8 -*-

# Define Python imports
import os
import sys
import time
import config
import threading
import math
import logging
import logging.handlers


# Define Custom imports
from Database import Database
from Orders import Orders

formater_str = '%(asctime)s,%(msecs)d %(levelname)s %(name)s: %(message)s'
formatter = logging.Formatter(formater_str)
datefmt="%Y-%b-%d %H:%M:%S"

LOGGER_ENUM = {'debug':'debug.log', 'trading':'trades.log','errors':'general.log'}
#LOGGER_FILE = LOGGER_ENUM['pre']
LOGGER_FILE = "binance-trader.log"
FORMAT = '%(asctime)-15s - %(levelname)s:  %(message)s'

logger = logging.basicConfig(filename=LOGGER_FILE, filemode='a',
                             format=formater_str, datefmt=datefmt,
                             level=logging.INFO)

# Approximated value to get back the commission for sell and buy
TOKEN_COMMISION = 0.001
BNB_COMMISION   = 0.0005
#((eth*0.05)/100)

class Trading2():

    # Define trade vars
    order_id = 0

    buying = False

    buy_filled = True
    sell_filled = True

    buy_filled_qty = 0
    sell_filled_qty = 0

    # percent (When you drop 10%, sell panic.)
    stop_loss = 0

    # Buy/Sell qty
    quantity = 0

    # BTC amount
    amount = 0

    # float(step_size * math.floor(float(free)/step_size))
    step_size = 0

    # Define static vars
    WAIT_TIME_BUY_SELL = 1 # seconds
    WAIT_TIME_CHECK_BUY_SELL = 0.2 # seconds
    WAIT_TIME_CHECK_SELL = 5 # seconds
    WAIT_TIME_STOP_LOSS = 20 # seconds

    MAX_TRADE_SIZE = 7 # int

    # Type of commision, Default BNB_COMMISION
    commision = BNB_COMMISION

    def __init__(self, option):
        print("options: {0}".format(option))

        # Get argument parse options
        self.option = option

        # Define parser vars
        self.order_id = self.option.orderid
        self.quantity = self.option.quantity
        self.wait_time = self.option.wait_time

        self.increasing = self.option.increasing
        self.decreasing = self.option.decreasing

        # BTC amount
        self.amount = self.option.amount

        # Type of commision
        if self.option.commision == 'TOKEN':
            self.commision = TOKEN_COMMISION

        # setup Logger
        self.logger =  self.setup_logger(self.option.symbol, debug=self.option.debug)

    def setup_logger(self, symbol, debug=True):
        """Function setup as many loggers as you want"""
        #handler = logging.FileHandler(log_file)
        #handler.setFormatter(formatter)
        #logger.addHandler(handler)
        logger = logging.getLogger(symbol)

        stout_handler = logging.StreamHandler(sys.stdout)
        if debug:
            logger.setLevel(logging.DEBUG)
            stout_handler.setLevel(logging.DEBUG)

        #handler = logging.handlers.SysLogHandler(address='/dev/log')
        #logger.addHandler(handler)
        stout_handler.setFormatter(formatter)
        logger.addHandler(stout_handler)
        return logger
    
    def log_debug(self, msg):
        self.logger.debug(msg)

    def log_info(self, msg):
        print(msg)
        self.logger.info(msg)

    def log_warn(self, msg):
        print(msg)
        self.logger.warn(msg)

    def buy(self, symbol, quantity, buyPrice, profitableSellingPrice):

        # Do you have an open order?
        self.check_not_buying()
        self.check_no_open_order()

        try:
            self.buying = True

            # Create order
            orderId = Orders.buy_limit(symbol, quantity, buyPrice)

            # Database log
            Database.write([orderId, symbol, 0, buyPrice, 'BUY', quantity, self.option.profit])

            self.log_info('%s : Buy order created. id:%d, q:%.8f, p:%.8f, Take profit aprox :%.8f' \
                          % (symbol, orderId, quantity, float(buyPrice), profitableSellingPrice))

            self.order_id = orderId

            return orderId

        except Exception as e:
            #print('bl: %s' % (e))
            self.log_warn('Buy error: %s' % (e))
            time.sleep(self.WAIT_TIME_BUY_SELL)
            return None
        finally:
            self.buying = False

    def sell(self, symbol, quantity, orderId, sell_price, last_price):

        '''
        The specified limit will try to sell until it reaches.
        If not successful, the order will be canceled.
        '''

        curt_order = Orders.get_order(symbol, orderId)

        if (curt_order['status'] == 'FILLED' and curt_order['side'] == 'SELL'):
            # sell order is filled.
            self.log_info('Sell order (Filled) Id: %d' % orderId)
            self.log_info('LastPrice : %.8f' % last_price)
            self.log_info('Profit: %%%s. Buy price: %.8f Sell price: %.8f' \
                          % (self.option.profit, float(sell_order['price']), sell_price))
            
            self.order_id = 0
            return

        if curt_order['status'] != 'FILLED' or curt_order['side'] != 'BUY':
            return

        # following is : BUY and FILLED

        sell_order = Orders.sell_limit(symbol, quantity, sell_price)

        sell_id = sell_order['orderId']
        self.log_info('Sell order create id: %d' % sell_id)

        self.order_id = sell_id

    def calc(self, lastBid):
        try:

            #Estimated sell price considering commision
            return lastBid + (lastBid * self.option.profit / 100) + (lastBid *self.commision)
            #return lastBid + (lastBid * self.option.profit / 100)

        except Exception as e:
            print('Calc Error: %s' % (e))
            return

    def check_no_open_order(self):
        # If there is an open order, exit.
        if self.order_id > 0:
            exit(1)
    
    def check_not_buying(self):
        if self.buying:
            exit(1)

    def action(self, symbol):
        #import ipdb; ipdb.set_trace()

        # Order amount
        quantity = self.quantity

        # Fetches the ticker price
        lastPrice = Orders.get_ticker(symbol)

        # Order book prices
        lastBid, lastAsk = Orders.get_order_book(symbol)

        # Target buy price, add little increase #87
        buyPrice = lastBid + self.increasing

        # Target sell price, decrease little 
        sellPrice = lastAsk - self.decreasing

        # Spread ( profit )
        profitableSellingPrice = self.calc(lastBid)

        # Check working mode
        # "range" or "profit"
        if self.option.mode == 'range':

            buyPrice = float(self.option.buyprice)
            sellPrice = float(self.option.sellprice)
            profitableSellingPrice = sellPrice

        # Screen log
        if self.option.prints and self.order_id == 0:
            spreadPerc = (lastAsk / lastBid - 1) * 100.0
            self.log_debug('price:%.8f buyprice:%.8f sellprice:%.8f bid:%.8f ask:%.8f spread:%.2f  Originalsellprice:%.8f' \
                          % (lastPrice, buyPrice, profitableSellingPrice, lastBid, lastAsk, spreadPerc, profitableSellingPrice-(lastBid *self.commision)   ))

        if self.order_id > 0: # 尝试提交sell

            # range mode
            if self.option.mode == 'range':
                profitableSellingPrice = self.option.sellprice

            '''
            If the order is complete, 
            try to sell it.
            '''

            # Perform buy action
            sellAction = threading.Thread(target=self.sell, args=(symbol, quantity, self.order_id, profitableSellingPrice, lastPrice,))
            sellAction.start()

            return

        '''
        Did profit get caught
        if ask price is greater than profit price, 
        buy with my buy price,    
        '''
        # order id is null
        if (lastAsk >= profitableSellingPrice and self.option.mode == 'profit') or \
                (lastPrice <= float(self.option.buyprice) and self.option.mode == 'range'):
            self.logger.info ("Mode: {0}, Lastask: {1}, Profit Sell Price {2}, ".format(self.option.mode, lastAsk, profitableSellingPrice))
            self.buy(symbol, quantity, buyPrice, profitableSellingPrice)

    def logic(self):
        return 0

    def filters(self):

        symbol = self.option.symbol

        # Get symbol exchange info
        symbol_info = Orders.get_info(symbol)

        if not symbol_info:
            #print('Invalid symbol, please try again...')
            self.logger.error('Invalid symbol, please try again...')
            exit(1)

        symbol_info['filters'] = {item['filterType']: item for item in symbol_info['filters']}

        return symbol_info

    def format_step(self, quantity, stepSize):
        return float(stepSize * math.floor(float(quantity)/stepSize))

    def validate(self):

        valid = True
        symbol = self.option.symbol
        filters = self.filters()['filters']

        # Order book prices
        lastBid, lastAsk = Orders.get_order_book(symbol)

        lastPrice = Orders.get_ticker(symbol)

        minQty = float(filters['LOT_SIZE']['minQty'])
        minPrice = float(filters['PRICE_FILTER']['minPrice'])
        quantity = float(self.option.quantity)

        # stepSize defines the intervals that a quantity/icebergQty can be increased/decreased by.
        stepSize = float(filters['LOT_SIZE']['stepSize'])

        # tickSize defines the intervals that a price/stopPrice can be increased/decreased by
        tickSize = float(filters['PRICE_FILTER']['tickSize'])

        # If option increasing default tickSize greater than
        if (float(self.option.increasing) < tickSize):
            self.increasing = tickSize

        # If option decreasing default tickSize greater than
        if (float(self.option.decreasing) < tickSize):
            self.decreasing = tickSize

        # Just for validation
        lastBid = lastBid + self.increasing

        # Set static
        # If quantity or amount is zero, minNotional increase 10%
        quantity = quantity + (quantity * 10 / 100)

        if self.amount > 0:
            # Calculate amount to quantity
            quantity = (self.amount / lastBid)

        if self.quantity > 0:
            # Format quantity step
            quantity = self.quantity

        quantity = self.format_step(quantity, stepSize)

        # Set Globals
        self.quantity = quantity
        self.step_size = stepSize

        # minQty = minimum order quantity
        if quantity < minQty:
            #print('Invalid quantity, minQty: %.8f (u: %.8f)' % (minQty, quantity))
            self.logger.error('Invalid quantity, minQty: %.8f (u: %.8f)' % (minQty, quantity))
            valid = False

        if lastPrice < minPrice:
            #print('Invalid price, minPrice: %.8f (u: %.8f)' % (minPrice, lastPrice))
            self.logger.error('Invalid price, minPrice: %.8f (u: %.8f)' % (minPrice, lastPrice))
            valid = False

        if not valid:
            exit(1)

    def run(self):

        cycle = 0
        actions = []

        symbol = self.option.symbol

        print('Validating...')

        # Validate symbol
        self.validate()

        print('Started...')
        print('Trading Symbol: %s' % symbol)
        print('Buy Quantity: %.8f' % self.quantity)
        print('Stop-Loss Amount: %s' % self.stop_loss)
        #print('Estimated profit: %.8f' % (self.quantity*self.option.profit))

        if self.option.mode == 'range':

           if self.option.buyprice == 0 or self.option.sellprice == 0:
               print('Please enter --buyprice / --sellprice\n')
               exit(1)

           print('Range Mode Options:')
           print('\tBuy Price: %.8f', self.option.buyprice)
           print('\tSell Price: %.8f', self.option.sellprice)

        else:
            print('Profit Mode Options:')
            print('\tPreferred Profit: %0.2f%%' % self.option.profit)
            print('\tBuy Price : (Bid+ --increasing %.8f)' % self.increasing)
            print('\tSell Price: (Ask- --decreasing %.8f)' % self.decreasing)

        print('\n')

        startTime = time.time()

        while (cycle <= self.option.loop):

           startTime = time.time()

           actionTrader = threading.Thread(target=self.action, args=(symbol,))
           actions.append(actionTrader)
           actionTrader.start()

           endTime = time.time()

           if endTime - startTime < self.wait_time:

               time.sleep(self.wait_time - (endTime - startTime))

               # 0 = Unlimited loop
               if self.option.loop > 0:
                   cycle = cycle + 1
