import logging
import ask_sdk_core.utils as ask_utils

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.dispatch_components import AbstractExceptionHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response
from ask_sdk_model.ui import SimpleCard

from coinbase.wallet.client import Client
import pandas as pd
import nicehash
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Read .env file
from dotenv import load_dotenv 
load_dotenv()

# Temporarily suppress FutureWarning messages
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# Store secrets/keys to variables
coinbase_api_key = os.environ.get('coinbase_api_key')
coinbase_api_secret = os.environ.get('coinbase_api_secret')
nicehash_api_key = os.environ.get('nicehash_api_key')
nicehash_api_secret = os.environ.get('nicehash_api_secret')
nicehash_org_id = os.environ.get('nicehash_org_id')
nicehash_api_url = 'https://api2.nicehash.com'

#############################
### Login to Coinbase API ###
#############################
client = Client(coinbase_api_key, coinbase_api_secret, api_version='2022-01-31')

# Get Coinbase wallet balance
df = pd.DataFrame()
accounts = client.get_accounts()

for i in accounts['data']:
    df = df.append(i['balance'], ignore_index=True)

# Get USD conversion
usd = []
for i in accounts['data']:
    usd.append(client.get_spot_price(currency_pair = i['balance']['currency'] + '-USD').amount)

df['USD'] = usd

# Convert Coinbase wallet balance to USD
df['amount-USD'] = pd.to_numeric(df['amount']) * pd.to_numeric(df['USD'])

# Add wallet source column
df['wallet'] = 'Coinbase'

#############################
### Login to NiceHash API ###
#############################
host = nicehash_api_url
organisation_id = nicehash_org_id
key = nicehash_api_key
secret = nicehash_api_secret

# Create public api object
public_api = nicehash.public_api(host, True)

# Get all curencies
currencies = public_api.get_currencies()

# Create private api object
private_api = nicehash.private_api(host, organisation_id, key, secret, True)

# Get balance for BTC address
my_btc_account = private_api.get_accounts_for_currency(currencies['currencies'][0]['symbol'])
df_nicehash = pd.DataFrame(my_btc_account.items()).T

df_nicehash.columns = df_nicehash.iloc[0] 
df_nicehash = df_nicehash.reindex(df_nicehash.index.drop(0)).reset_index(drop=True)
df_nicehash.columns.name = None
df_nicehash = df_nicehash.rename(columns={"available": "amount"})

# Get USD BTC price
usd_btc = []
for i in df_nicehash['currency']:
    usd_btc.append(client.get_spot_price(currency_pair = i + '-USD').amount)

df_nicehash['USD'] = usd_btc

# Convert NiceHash wallet balance to USD
df_nicehash['amount-USD'] = pd.to_numeric(df_nicehash['amount']) * pd.to_numeric(df_nicehash['USD'])

# Add wallet source column
df_nicehash['wallet'] = 'NiceHash'

# Combine NiceHash and Coinbase DataFrames
df_nicehash = df_nicehash[['amount','currency','USD','amount-USD', 'wallet']]
frames = [df, df_nicehash]
result = pd.concat(frames, join="outer")

# Return only non-zero values
result = result[(result.select_dtypes(include=['number']) != 0).any(1)]

# Get list of active mining rigs
rig_list = private_api.get_rigs()
rig_list = rig_list['groups']['']['rigs']
rig_list = [i for i in rig_list]
df_rig_list = pd.DataFrame(rig_list)

class LaunchRequestHandler(AbstractRequestHandler):
    """Handler for Skill Launch."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        total_amount = "You have a total of: $" + str('{:.2f}'.format(round(result['amount-USD'].sum(),2))) + "."
        speak_output = total_amount + "\n\nTo learn more about your balances, say \"more info\". You can also say things like start or stop mining. When you are finished, just say \"exit\"."
        main_title = "Welcome to My Crypto, here is your crypto balance"
        main_text = total_amount + "\n\nTo learn more about your balances, say \"more info\"."

        return (
            handler_input.response_builder
                .speak(speak_output)
                .set_card(SimpleCard(main_title, main_text))
                .ask(speak_output)
                .response
        )

class CryptoBalanceHandler(AbstractRequestHandler):
    """Handler for crypto balance."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("CryptoBalance")(handler_input)
    
    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        total_amount = "You have a total of: $" + str('{:.2f}'.format(round(result['amount-USD'].sum(),2))) + "."
        speak_output = total_amount + "\n\nTo learn more about your balances, say \"more info\". You can also say things like start or stop mining. When you are finished, just say \"exit\"."
        main_title = "My Crypto: Total Balance"
        main_text = total_amount + "\n\nTo learn more about your balances, say \"more info\"."
        
        return (
            handler_input.response_builder
                .speak(speak_output)
                .set_card(SimpleCard(main_title, main_text))
                .ask(speak_output)
                .response
        )

class CryptoDetailHandler(AbstractRequestHandler):
    """Handler for additional balance information."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("CryptoDetail")(handler_input)
    
    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        amount_desc = []
        
        for i in result.values.tolist():
            amount_desc.append("Your balance in " + ', '.join([str(i[4])]) + " is $" + str('{:.2f}'.format(round(i[3],2))) + " (" + str(i[0]) + " " + str(i[1]) + ")" + ".")
            
        speak_output = '\n'.join('{}' for _ in range(len(amount_desc))).format(*amount_desc) + " When you are finished, just say \"exit\"."
        addn_title = "My Crypto: Additional Details"
        addn_text = '\n'.join('{}' for _ in range(len(amount_desc))).format(*amount_desc)

        return (
            handler_input.response_builder
                .speak(speak_output)
                .set_card(SimpleCard(addn_title, addn_text))
                .ask(speak_output)
                .response
        )

class StartMiningHandler(AbstractRequestHandler):
    """Handler for starting mining."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("StartMining")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        for i in df_rig_list['rigId']:
            private_api.rig_action(i, 'START')

        speak_output = "All rigs have started mining. When you are finished, say \"exit\", or \"more info\" for additional balance information."
        start_title = "My Crypto: Start Mining"
        start_text = "All rigs have started mining."

        return (
            handler_input.response_builder
                .speak(speak_output)
                .set_card(SimpleCard(start_title, start_text))
                .ask(speak_output)
                .response
        )

class StopMiningHandler(AbstractRequestHandler):
    """Handler for stopping mining."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("StopMining")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        for i in df_rig_list['rigId']:
            private_api.rig_action(i, 'STOP')

        speak_output = "All rigs have stopped mining. When you are finished, say \"exit\", or \"more info\" for additional balance information."
        stop_title = "My Crypto: Stop Mining"
        stop_text = "All rigs have stopped mining."

        return (
            handler_input.response_builder
                .speak(speak_output)
                .set_card(SimpleCard(stop_title, stop_text))
                .ask(speak_output)
                .response
        )

class HelpIntentHandler(AbstractRequestHandler):
    """Handler for Help Intent."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speak_output = "You can say things like \"start or stop mining\", \"get my balance\", or \"more info\". How can I help?"

        return (
            handler_input.response_builder
                .speak(speak_output)
                .ask(speak_output)
                .response
        )


class CancelOrStopIntentHandler(AbstractRequestHandler):
    """Single handler for Cancel and Stop Intent."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input) or
                ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input))

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speak_output = "Goodbye!"

        return (
            handler_input.response_builder
                .speak(speak_output)
                .response
        )

class FallbackIntentHandler(AbstractRequestHandler):
    """Single handler for Fallback Intent."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In FallbackIntentHandler")
        speech = "Hmm, I'm not sure. You can say things like \"start or stop mining\", \"get my balance\", or \"more info\". When you are finished, just say \"exit\"."
        reprompt = "I didn't catch that. What can I help you with?"

        return handler_input.response_builder.speak(speech).ask(reprompt).response

class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handler for Session End."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response

        # Any cleanup logic goes here.

        return handler_input.response_builder.response


class IntentReflectorHandler(AbstractRequestHandler):
    """The intent reflector is used for interaction model testing and debugging.
    It will simply repeat the intent the user said. You can create custom handlers
    for your intents by defining them above, then also adding them to the request
    handler chain below.
    """
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_request_type("IntentRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        intent_name = ask_utils.get_intent_name(handler_input)
        speak_output = "You just triggered " + intent_name + "."

        return (
            handler_input.response_builder
                .speak(speak_output)
                # .ask("add a reprompt if you want to keep the session open for the user to respond")
                .response
        )


class CatchAllExceptionHandler(AbstractExceptionHandler):
    """Generic error handling to capture any syntax or routing errors. If you receive an error
    stating the request handler chain is not found, you have not implemented a handler for
    the intent being invoked or included it in the skill builder below.
    """
    def can_handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> bool
        return True

    def handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> Response
        logger.error(exception, exc_info=True)

        speak_output = "Sorry, I had trouble doing what you asked. Please try again."

        return (
            handler_input.response_builder
                .speak(speak_output)
                .ask(speak_output)
                .response
        )

# The SkillBuilder object acts as the entry point for your skill, routing all request and response
# payloads to the handlers above. Make sure any new handlers or interceptors you've
# defined are included below. The order matters - they're processed top to bottom.


sb = SkillBuilder()

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(CryptoBalanceHandler())
sb.add_request_handler(CryptoDetailHandler())
sb.add_request_handler(StartMiningHandler())
sb.add_request_handler(StopMiningHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_request_handler(IntentReflectorHandler()) # make sure IntentReflectorHandler is last so it doesn't override your custom intent handlers

sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()