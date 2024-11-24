# bitcoin_trading_bot.py

import ccxt
import pandas as pd
import time
from datetime import datetime, timezone, timedelta


class BitcoinTradingBot:

    def __init__(self, api_key, secret_key, password, investment_ratio=1.0):
        self.investment_ratio = max(0.1, min(1.0, investment_ratio))
        self.exchange = ccxt.okx({
            'apiKey': api_key,
            'secret': secret_key,
            'password': password,
            'options': {
                'defaultType': 'swap'
            }
        })
        self.symbol = 'BTC/USDT:USDT'
        self.timeframe = '15m'
        self.position = None
        self.entry_price = None
        self.initial_balance = None
        self.take_profit_rate = 0.0007
        self.leverage = 50
        self.heartbeat_count = 0

        self.setup_trading_config()
        self.update_initial_balance()

    def update_initial_balance(self):
        """
        현재 계좌 잔고를 가져와서 초기 자산 설정
        """
        try:
            balance = self.exchange.fetch_balance()
            if 'USDT' in balance and 'free' in balance['USDT']:
                try:
                    balance_value = balance['USDT']['free']
                    # 문자열로 변환 후 float로 변환
                    self.initial_balance = float(str(balance_value))
                    print(f"현재 자산: {self.initial_balance} USDT")

                    # None 체크 추가
                    if self.initial_balance is None or self.initial_balance <= 0:
                        print("투자 가능한 자본이 없습니다")
                        self.initial_balance = 0
                        raise SystemExit("No available capital")
                except (ValueError, TypeError):
                    print("Error: Invalid balance value")
                    self.initial_balance = 0
            else:
                print("Error: Could not find USDT balance")
                self.initial_balance = 0
        except SystemExit as se:
            raise se
        except Exception as e:
            print(f"Error updating balance: {e}")
            self.initial_balance = 0

    def setup_trading_config(self):
        try:
            for pos_side in ['long', 'short']:
                self.exchange.set_leverage(self.leverage,
                                           self.symbol,
                                           params={
                                               'mgnMode': 'cross',
                                               'posSide': pos_side,
                                               'lever': str(self.leverage)
                                           })
                print(f"{pos_side} 포지션 레버리지 설정 완료: {self.leverage}x")
            print("마진 모드 설정 완료: 교차 마진")
        except Exception as e:
            print(f"거래 설정 중 오류 발생: {e}")

    def calculate_stop_loss_rate(self):
        try:
            balance = self.exchange.fetch_balance()
            if 'USDT' not in balance or 'free' not in balance['USDT']:
                print("Error: Cannot fetch USDT balance")
                return 0.001

            current_balance = float(str(balance['USDT']['free']))

            if current_balance <= 0:
                print("투자 가능한 자본이 없습니다")
                raise SystemExit("No available capital")

            if not self.initial_balance or self.initial_balance == 0:
                print("Error: Initial balance is not set properly")
                return 0.001

            profit_rate = (current_balance / self.initial_balance) - 1
            stop_loss_rate = max(profit_rate - 0.01, 0.001)
            return stop_loss_rate

        except SystemExit as se:
            raise se
        except Exception as e:
            print(f"Error calculating stop loss rate: {e}")
            return 0.001

    def calculate_position_size(self):
        try:
            balance = self.exchange.fetch_balance()
            if 'USDT' not in balance or 'free' not in balance['USDT']:
                print("Error: Cannot fetch USDT balance")
                return 0
            balance_value = float(str(balance['USDT']['free']))

            available_balance = balance_value * self.investment_ratio

            ticker = self.exchange.fetch_ticker(self.symbol)
            if 'last' not in ticker or ticker['last'] is None:
                print("Error: Cannot fetch current price")
                return 0
            price = float(str(ticker['last']))

            if price <= 0:
                print("Error: Invalid price (zero or negative)")
                return 0

            position_size = (available_balance * float(self.leverage)) / price
            position_size = round(position_size, 8)

            print(
                f"Available balance for trading: {available_balance} USDT ({self.investment_ratio*100}% of free)"
            )
            print(f"Calculated position size: {position_size} BTC")
            return position_size

        except Exception as e:
            print(f"Error calculating position size: {e}")
            return 0

    def get_historical_data(self):
        try:
            candles = self.exchange.fetch_ohlcv(symbol=self.symbol,
                                                timeframe=self.timeframe,
                                                limit=4)

            if not candles or len(candles) < 4:
                print("Error: Insufficient candle data")
                return pd.DataFrame()

            df_dict = {
                'timestamp': [int(str(c[0])) for c in candles],
                'open': [float(str(c[1])) for c in candles],
                'high': [float(str(c[2])) for c in candles],
                'low': [float(str(c[3])) for c in candles],
                'close': [float(str(c[4])) for c in candles],
                'volume': [float(str(c[5])) for c in candles]
            }

            df = pd.DataFrame(df_dict)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            print(f"Successfully fetched {len(df)} candles")
            return df

        except Exception as e:
            print(f"Error fetching historical data: {e}")
            return pd.DataFrame()

    def check_three_tick_rule(self, df):
        if len(df) < 4:
            print("Error: Not enough data to check 3-tick rule.")
            return None

        last_three = df.iloc[-4:-1]
        candle_colors = (last_three['close'] > last_three['open']).values

        if not any(candle_colors):
            return 'long'
        elif all(candle_colors):
            return 'short'

        return None

    def check_existing_position(self):
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            for position in positions:
                if float(position['contracts']) > 0:
                    self.position = 'long' if position[
                        'side'] == 'long' else 'short'
                    self.entry_price = float(position['entryPrice'])
                    return True
            return False
        except Exception as e:
            print(f"포지션 확인 중 오류 발생: {e}")
            return False

    def is_position_closed(self):
        if not self.position or not self.entry_price:
            return True

        try:
            positions = self.exchange.fetch_positions([self.symbol])
            return all(
                float(position['contracts']) == 0 for position in positions)
        except Exception as e:
            print(f"포지션 종료 확인 중 오류 발생: {e}")
            return False

    def create_order_with_retry(self, *args, **kwargs):
        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            try:
                return self.exchange.create_order(*args, **kwargs)
            except Exception as e:
                print(f"Error creating order, attempt {attempt + 1}: {e}")
                time.sleep(2)
        print("Max retries reached, order creation failed.")
        return None

    def execute_trade(self, signal):
        if self.check_existing_position():
            print("이미 활성화된 포지션이 있습니다. 익절 또는 손절 대기 중...")
            return

        try:
            amount = self.calculate_position_size()
            if amount == 0:
                print("Error: Invalid position size, skipping trade.")
                return

            order = self.create_order_with_retry(
                symbol=self.symbol,
                type='market',
                side='buy' if signal == 'long' else 'sell',
                amount=amount)

            if order and 'average' in order:
                try:
                    self.entry_price = float(str(order['average']))
                    if self.entry_price <= 0:
                        print("Error: Invalid entry price (zero or negative)")
                        return
                except (ValueError, TypeError) as e:
                    print(f"Error converting entry price: {e}")
                    print(f"Raw average price value: {order['average']}")
                    return
            else:
                print(
                    "Error: Order execution failed or average price not found."
                )
                return

            self.position = signal

            take_profit_price = self.entry_price * (
                1 + self.take_profit_rate
            ) if signal == 'long' else self.entry_price * (
                1 - self.take_profit_rate)

            self.create_order_with_retry(
                symbol=self.symbol,
                type='limit',
                side='sell' if signal == 'long' else 'buy',
                amount=amount,
                price=float(str(take_profit_price)),
                params={
                    'reduceOnly': True,
                    'postOnly': True
                })

            stop_loss_rate = self.calculate_stop_loss_rate()
            stop_loss_price = self.entry_price * (
                1 - stop_loss_rate
            ) if signal == 'long' else self.entry_price * (1 + stop_loss_rate)

            self.create_order_with_retry(
                symbol=self.symbol,
                type='stop',
                side='sell' if signal == 'long' else 'buy',
                amount=amount,
                price=float(str(stop_loss_price)),
                params={
                    'reduceOnly': True,
                    'stopPrice': float(str(stop_loss_price))
                })

            # 강조된 거래 체결 알림
            print("\n" + "=" * 50)
            print("\n🔔 신규 포지션 진입 알림 🔔".center(50))
            print("=" * 50)
            print(f"시간: {datetime.now(timezone(timedelta(hours=9)))}")
            print(f"포지션: {'롱' if signal == 'long' else '숏'}")
            print(f"진입가격: {self.entry_price} USDT")
            print(f"수량: {amount} BTC")
            print(f"레버리지: {self.leverage}x")
            print(
                f"투자금액: {amount * self.entry_price / self.leverage:.2f} USDT")
            print(
                f"익절가: {take_profit_price:.2f} USDT (예상수익: {self.take_profit_rate*100:.2f}%)"
            )
            print(
                f"손절가: {stop_loss_price:.2f} USDT (예상손실: {stop_loss_rate*100:.2f}%)"
            )
            print("=" * 50 + "\n")

        except Exception as e:
            print(f"Error executing trade: {e}")

    def show_heartbeat(self):
        """
        프로그램 실행 상태 표시
        """
        self.heartbeat_count += 1
        kst = timezone(timedelta(hours=9))
        current_time = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")

        if self.heartbeat_count % 15 == 0:
            try:
                balance = self.exchange.fetch_balance()
                current_balance = float(
                    str(balance['USDT']['free'])
                ) if 'USDT' in balance and 'free' in balance['USDT'] else 0.0
                available_for_trading = current_balance * self.investment_ratio

                print("\n" + "=" * 50)
                print(f"Bot Status Update - {current_time}")
                print(f"Current Balance: {current_balance:.2f} USDT")
                print(f"Investment Ratio: {self.investment_ratio*100}%")
                print(
                    f"Available for Trading: {available_for_trading:.2f} USDT")
                if self.position:
                    print(
                        f"Current Position: {self.position} at {self.entry_price}"
                    )
                print("=" * 50 + "\n")
            except Exception as e:
                print(f"Error in heartbeat status update: {e}")
        else:
            print(f"Bot running... {current_time}", end='\r')

    def run(self):
        """
        매매봇 실행
        """
        try:
            print("Starting Bitcoin Trading Bot...")

            # None 체크 추가
            if self.initial_balance is None or self.initial_balance <= 0:
                print("투자 가능한 자본이 없습니다")
                return

            print(f"Initial Balance: {self.initial_balance} USDT")
            print(f"Investment Ratio: {self.investment_ratio*100}%")
            print(f"Leverage: {self.leverage}x")

            while True:
                try:
                    self.show_heartbeat()

                    current_time = datetime.now().minute
                    if current_time % 15 == 0:
                        self.update_initial_balance()

                        # 업데이트된 잔고 체크
                        if self.initial_balance is None or self.initial_balance <= 0:
                            print("투자 가능한 자본이 없습니다")
                            return

                        if self.check_existing_position():
                            print("활성 포지션 확인됨 - 새로운 진입 대기 중...")
                            if self.is_position_closed():
                                print("포지션이 종료되었습니다. 새로운 진입 가능")
                                self.position = None
                                self.entry_price = None
                            else:
                                time.sleep(60 * 14)
                                continue

                        df = self.get_historical_data()
                        if df.empty:
                            print("Error: No historical data to process.")
                            time.sleep(60)
                            continue

                        signal = self.check_three_tick_rule(df)

                        if signal:
                            self.execute_trade(signal)

                        time.sleep(60 * 14)

                    time.sleep(1)

                except SystemExit as se:
                    print("Trading bot terminated due to insufficient capital")
                    return
                except Exception as e:
                    print(f"Error in main loop: {e}")
                    time.sleep(5)

        except Exception as e:
            print(f"Fatal error in trading bot: {e}")


if __name__ == "__main__":
    API_KEY = "8754eef5-5963-4c05-8631-89fc1ba5a4a0"
    SECRET_KEY = "D31C8F2ED8760B3DD7DA0C6419AF6944"
    PASSWORD = "@Oemflqmf100"

    investment_ratio = 0.1

    bot = BitcoinTradingBot(API_KEY, SECRET_KEY, PASSWORD, investment_ratio)
    bot.run()
