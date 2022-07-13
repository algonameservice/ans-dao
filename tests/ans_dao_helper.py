'''
Copyright (c) 2022 Algorand Name Service

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

from multiprocessing.connection import answer_challenge
from algosdk import mnemonic, account, encoding, constants
from algosdk.future import transaction
from algosdk.future.transaction import LogicSig, LogicSigTransaction, LogicSigAccount
from algosdk.v2client import algod, indexer
from algosdk import logic, util
import json, random
from numpy import int64
from pyteal import *
import ans_helper as anshelper
import hashlib

import sys
#sys.path.append('../')

sys.path.insert(0,'..')

#from contracts.dao_app_approval import approval_program
from contracts.dao_app_approval import approval_program
from contracts.dao_app_clear import clear_state_program

import base64
import datetime,time
# Import PureStake API
import mysecrets


def SetupClient(network):

	if(network=="sandbox"):
		# Local sandbox node 
		algod_address = "http://localhost:4001"
		algod_token = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

	elif(network=="purestake"):
		# Purestake conn
		algod_address = "https://testnet-algorand.api.purestake.io/ps2"
		algod_token = mysecrets.MY_PURESTAKE_TOKEN
		headers = {
			"X-API-Key": mysecrets.MY_PURESTAKE_TOKEN
		}
	
	else:
		raise ValueError

	algod_client=algod.AlgodClient(algod_token, algod_address, headers=headers)
	return algod_client

def SetupIndexer(network):
	if(network=="purestake"):
		algod_address = "https://testnet-algorand.api.purestake.io/idx2"
		headers = {
			'X-API-key' : mysecrets.MY_PURESTAKE_TOKEN,
		}
		algod_indexer=indexer.IndexerClient("", algod_address, headers)
	
	return algod_indexer

def GetFundingAccount(algod_client):

	# address: KLRZGUWF5WDUWZXSGCWA723FLZXMQ4GIPXD2UYJ6C74X3N3NES4QH5XIF4
	passphrase= mysecrets.MNEMONIC
	private_key = mnemonic.to_private_key(passphrase)
	sender = account.address_from_private_key(private_key)
	#print("Sender address: {}".format(sender))

	account_info = algod_client.account_info(sender)
	print("Funding account balance: {} microAlgos".format(account_info.get('amount')))

	return sender, passphrase

def GenerateAccount():
	new_private_key, new_address = account.generate_account()
	#print("New address: {}".format(new_address))
	#print("Passphrase: {}".format(mnemonic.from_private_key(new_private_key)))
	return new_address, mnemonic.from_private_key(new_private_key)

def FundNewAccount(algod_client, receiver, amount, funding_acct_mnemonic):

	sender_private_key=mnemonic.to_private_key(funding_acct_mnemonic)
	sender=account.address_from_private_key(sender_private_key)

	unsigned_txn = transaction.PaymentTxn(sender, algod_client.suggested_params(), receiver,amount, None)
	signed_txn = unsigned_txn.sign(sender_private_key)

	#submit transaction
	txid = algod_client.send_transaction(signed_txn)
	#print("Successfully sent transaction with txID: {}".format(txid))
	print("Successfully sent transaction")

	# wait for confirmation 
	try:
		confirmed_txn = wait_for_confirmation(algod_client,txid)  
	except Exception as err:
		print(err)
		return

	#print("Transaction information: {}".format(
	#    json.dumps(confirmed_txn, indent=4)))

def DeployANSToken(algod_client, asa_owner_mnemonic):

	pk_asa = mnemonic.to_private_key(asa_owner_mnemonic)
	sender_asa_deploy = account.address_from_private_key(pk_asa)

	txn = transaction.AssetConfigTxn(
		sender=sender_asa_deploy,
		sp=algod_client.suggested_params(),
		total=20000000000, #200M.00
		default_frozen=False,
		manager=sender_asa_deploy,
		strict_empty_address_check=False,
		unit_name="ANS",
		asset_name="AlgorandNameService",
		url="https://algonameservice.com/token", 
		decimals=2
	)

	stxn = txn.sign(pk_asa)

	txid = algod_client.send_transaction(stxn)

	# wait for confirmation 
	try:
		confirmed_txn = wait_for_confirmation(algod_client,txid)  
		return confirmed_txn["asset-index"]
	except Exception as err:
		print(err)
		return

def IsOptedInASA(algod_client_in, account, asaid):
	params = algod_client_in.suggested_params()
	
	account_info = algod_client_in.account_info(account)
	holding = False
	idx = 0
	for my_account_info in account_info['assets']:
		scrutinized_asset = account_info['assets'][idx]
		idx = idx + 1    
		if (scrutinized_asset['asset-id'] == asaid):
			holding = True
			break
	return holding

def ASAOptIn(algod_client_in, pk_account, asaid):

	sender_asa_optin = account.address_from_private_key(pk_account)
	
	if not IsOptedInASA(algod_client_in, sender_asa_optin, asaid):
	
		# Use the AssetTransferTxn class to transfer assets and opt-in
		txn = transaction.AssetOptInTxn(
			sender=sender_asa_optin,
			sp=algod_client_in.suggested_params(),
			index=asaid,
			rekey_to=None)
		stxn = txn.sign(pk_account)
		txid = algod_client_in.send_transaction(stxn)

		try:
			wait_for_confirmation(algod_client_in, txid)
			print_asset_holding(algod_client_in, sender_asa_optin, asaid)
		except Exception as err:
			print(err)


def TransferASA(algod_client_in, amount, pk_sender, acct_receiver, asaid):
	acct_sender = account.address_from_private_key(pk_sender)
	
	assert(IsOptedInASA(algod_client_in, acct_receiver, asaid))
	
	# Use the AssetTransferTxn class to transfer assets and opt-in
	txn = transaction.AssetTransferTxn(
		sender=acct_sender,
		sp=algod_client_in.suggested_params(),
		receiver=acct_receiver,
		amt=amount,
		index=asaid,
		close_assets_to=None,
		revocation_target=None,
		rekey_to=None)
	stxn = txn.sign(pk_sender)
	txid = algod_client_in.send_transaction(stxn)

	try:
		wait_for_confirmation(algod_client_in, txid)
		print_asset_holding(algod_client_in, acct_receiver, asaid)
	except Exception as err:
		print(err)

#   Utility function used to print asset holding for account and assetid
def print_asset_holding(algodclient, account, assetid):
	# note: if you have an indexer instance available it is easier to just use this
	# response = myindexer.accounts(asset_id = assetid)
	# then use 'account_info['created-assets'][0] to get info on the created asset

	account_info = algodclient.account_info(account)
	idx = 0
	for my_account_info in account_info['assets']:
		scrutinized_asset = account_info['assets'][idx]
		idx = idx + 1        
		if (scrutinized_asset['asset-id'] == assetid):
			print("Asset ID: {}".format(scrutinized_asset['asset-id']))
			print(json.dumps(scrutinized_asset, indent=4))
			break

def print_created_asset(algodclient, account, assetid):    
	# note: if you have an indexer instance available it is easier to just use this
	# response = myindexer.accounts(asset_id = assetid)
	# then use 'account_info['created-assets'][0] to get info on the created asset
	account_info = algodclient.account_info(account)
	idx = 0
	for my_account_info in account_info['created-assets']:
		scrutinized_asset = account_info['created-assets'][idx]
		idx = idx + 1       
		if (scrutinized_asset['index'] == assetid):
			print("Asset ID: {}".format(scrutinized_asset['index']))
			print(json.dumps(my_account_info['params'], indent=4))
			break

def DeployANSDAO(algod_client: algod,
	min_support: int64,
	min_duration: int64,
	contract_owner_mnemonic: str, 
	gov_asaid: int64
	):

	pk_owner=mnemonic.to_private_key(contract_owner_mnemonic)
	acct_owner=account.address_from_private_key(pk_owner)

	# Setup Schema
	local_ints = 4 
	local_bytes = 12 
	global_ints = 32 
	global_bytes = 32 
	global_schema = transaction.StateSchema(global_ints, global_bytes)
	local_schema = transaction.StateSchema(local_ints, local_bytes)
	
	on_complete = transaction.OnComplete.NoOpOC.real
	min_deposit = 20000000
	#min_support = 20000#00
	#min_duration = 2 # days
	max_duration = 60 # days
	appargs = [
		min_deposit.to_bytes(8, 'big'), # min deposit
		min_support.to_bytes(8, 'big'), # min support
		min_duration.to_bytes(8, 'big'), # min duration
		max_duration.to_bytes(8, 'big'), # max duration
		"https://ansdao.org".encode('utf-8') #url
	]
	
	compiled_approval_program = compileTeal(approval_program(gov_asaid), Mode.Application, version=6)
	compiled_clear_state_program = compileTeal(clear_state_program(), Mode.Application,version=6)

	
	
	#ans_approval_program = compile_program(algod_client, import_teal_source_code_as_binary('dao_app_approval.teal'))
	#ans_clear_state_program = compile_program(algod_client, import_teal_source_code_as_binary('dao_app_clear_state.teal'))

	ans_approval_program = compile_program(algod_client, str.encode(compiled_approval_program))
	ans_clear_state_program = compile_program(algod_client,str.encode(compiled_clear_state_program))

	h = hashlib.new('sha256')
	h.update(ans_approval_program)
	print(h.hexdigest())
	
	txn = transaction.ApplicationCreateTxn(
		sender=acct_owner,
		sp=algod_client.suggested_params(), 
		on_complete=on_complete,
		approval_program=ans_approval_program, 
		clear_program=ans_clear_state_program,
		global_schema=global_schema,
		local_schema=local_schema,
		app_args=appargs,
		foreign_assets=[gov_asaid]
	)
	
	# sign transaction
	signed_txn = txn.sign(pk_owner)
	tx_id = signed_txn.transaction.get_txid()
	
	# send transaction
	algod_client.send_transactions([signed_txn])

	try:	
		# await confirmation
		wait_for_confirmation(algod_client, tx_id)
	
		# display results
		transaction_response = algod_client.pending_transaction_info(tx_id)
		app_id = transaction_response['application-index']
	
		return app_id
	except Exception as err:
		print(err)

def DAOOptInToGOVASA(algod_client, pk_sender, gov_asaid, dao_app_id):
	acct_sender=account.address_from_private_key(pk_sender)
	appargs = ["opt_in_to_gov_token"]

	txn = transaction.ApplicationNoOpTxn(
		sender=acct_sender,
		sp=algod_client.suggested_params(),
		index=dao_app_id,
		foreign_assets=[gov_asaid],
		app_args=appargs
	)

	signed_txn = txn.sign(pk_sender)
	tx_id = signed_txn.transaction.get_txid()
	
	try:
		algod_client.send_transaction(signed_txn)
		wait_for_confirmation(algod_client, tx_id)
	except Exception as err:
		print(err)

def DAOAddProposalSocial(
	algod_client: algod,
	pk_sender: str,
	duration: int64,
	gov_asaid: int64,
	deposit_amt: int64,
	dao_app_id: int64
	):

	Grp_txns_unsign = []

	deposit_txn = transaction.AssetTransferTxn(
		sender=account.address_from_private_key(pk_sender),
		sp=algod_client.suggested_params(),
		amt=deposit_amt,
		receiver=logic.get_application_address(dao_app_id),
		index=gov_asaid
		#rekey_to=constants.ZERO_ADDRESS,
		#close_assets_to=constants.ZERO_ADDRESS
	)
	
	Grp_txns_unsign.append(deposit_txn)

	txn_add_proposal = transaction.ApplicationNoOpTxn(
		sender=account.address_from_private_key(pk_sender),
		sp=algod_client.suggested_params(),
		index=dao_app_id,
		app_args=[
			"add_proposal".encode("utf-8"),
			"social".encode("utf-8"),
			duration.to_bytes(8, 'big'),
			"https://github.com/someproposal"
		]
		#rekey_to=constants.ZERO_ADDRESS
	)

	
	Grp_txns_unsign.append(txn_add_proposal)

	Grp_txns_packed_unsigned = transaction.assign_group_id(Grp_txns_unsign)
	Grp_txns_signed = []
	
	for i in range(2):
		Grp_txns_signed.append(Grp_txns_unsign[i].sign(pk_sender))
	
	try:
		txn_id = Grp_txns_signed[1].transaction.get_txid()
		algod_client.send_transactions(Grp_txns_signed)
		wait_for_confirmation(algod_client, txn_id)
	except Exception as err:
		print(err)

def DAOAddProposalFunding(
	algod_client: algod,
	pk_sender: str,
	duration: int64,
	gov_asaid: int64,
	deposit_amt: int64,
	dao_app_id: int64,
	reg_app_id: int64,
	amt_algos: int64,
	amt_ans: int64,
	addr_recipient: int64
):

	Grp_txns_unsign = []

	deposit_txn = transaction.AssetTransferTxn(
		sender=account.address_from_private_key(pk_sender),
		sp=algod_client.suggested_params(),
		amt=deposit_amt,
		receiver=logic.get_application_address(dao_app_id),
		index=gov_asaid,
	)
	
	Grp_txns_unsign.append(deposit_txn)

	txn_add_proposal = transaction.ApplicationNoOpTxn(
		sender=account.address_from_private_key(pk_sender),
		sp=algod_client.suggested_params(),
		index=dao_app_id,
		foreign_apps=[reg_app_id],
		accounts=[addr_recipient, logic.get_application_address(reg_app_id)],
		app_args=[
			"add_proposal".encode("utf-8"),
			"funding".encode("utf-8"),
			duration.to_bytes(8, 'big'),
			"https://github.com/someproposal".encode("utf-8"),
			amt_algos.to_bytes(8, 'big'),
			amt_ans.to_bytes(8, 'big')
		]
		#rekey_to=constants.ZERO_ADDRESS
	)
	
	Grp_txns_unsign.append(txn_add_proposal)

	Grp_txns_packed_unsigned = transaction.assign_group_id(Grp_txns_unsign)
	Grp_txns_signed = []
	
	for i in range(2):
		Grp_txns_signed.append(Grp_txns_unsign[i].sign(pk_sender))
	
	try:
		txn_id = Grp_txns_signed[1].transaction.get_txid()
		algod_client.send_transactions(Grp_txns_signed)
		wait_for_confirmation(algod_client, txn_id)
	except Exception as err:
		print(err)

def DAOAddProposalUpdateReg(
	algod_client: algod,
	pk_sender: str,
	duration: int64,
	gov_asaid: int64,
	deposit_amt: int64,
	dao_app_id: int64,
	reg_app_id: int64,
	addr_recipient: int64
):

	Grp_txns_unsign = []

	deposit_txn = transaction.AssetTransferTxn(
		sender=account.address_from_private_key(pk_sender),
		sp=algod_client.suggested_params(),
		amt=deposit_amt,
		receiver=logic.get_application_address(dao_app_id),
		index=gov_asaid,
	)
	
	Grp_txns_unsign.append(deposit_txn)
	
	compiled_approval_program = anshelper.compileTeal(anshelper.approval_program(logic.get_application_address(dao_app_id)), Mode.Application,version=6)
	compiled_clear_state_program = anshelper.compileTeal(anshelper.clear_state_program(), Mode.Application,version=6)

	ans_app_program = anshelper.compile_program(algod_client, str.encode(compiled_approval_program))
	ans_clear_program = anshelper.compile_program(algod_client, str.encode(compiled_clear_state_program))

	txn_add_proposal = transaction.ApplicationNoOpTxn(
		sender=account.address_from_private_key(pk_sender),
		sp=algod_client.suggested_params(),
		index=dao_app_id,
		foreign_apps=[reg_app_id],
		accounts=[addr_recipient, logic.get_application_address(reg_app_id)],
		app_args=[
			"add_proposal".encode("utf-8"),
			"updatereg".encode("utf-8"),
			duration.to_bytes(8, 'big'),
			"https://github.com/someproposal".encode("utf-8"),
			reg_app_id.to_bytes(8, 'big'),
			ans_app_program,
			ans_clear_program
		],
		#rekey_to=constants.ZERO_ADDRESS
	)
	
	Grp_txns_unsign.append(txn_add_proposal)

	transaction.assign_group_id(Grp_txns_unsign)
	Grp_txns_signed = []
	
	for i in range(2):
		Grp_txns_signed.append(Grp_txns_unsign[i].sign(pk_sender))
	
	try:
		txn_id = Grp_txns_signed[1].transaction.get_txid()
		algod_client.send_transactions(Grp_txns_signed)
		wait_for_confirmation(algod_client, txn_id)
	except Exception as err:
		print(err)

def DAORegisterVote(
	algod_client: algod,
	choice: str,
	pvk_sender: str ,
	gov_asaid: int64, 
	dao_app_id: int64):

	txn_dao_opt_in = transaction.ApplicationOptInTxn(
		sender=account.address_from_private_key(pvk_sender),
		sp=algod_client.suggested_params(),
		index=dao_app_id
	)

	try:
		txn_id = txn_dao_opt_in.get_txid()
		algod_client.send_transaction(txn_dao_opt_in.sign(pvk_sender))
		wait_for_confirmation(algod_client, txn_id)
	except Exception as err:
		print(err)

	txn_register_vote = transaction.ApplicationNoOpTxn(
		sender=account.address_from_private_key(pvk_sender),
		sp=algod_client.suggested_params(),
		index=dao_app_id,
		app_args=[
			"register_vote".encode("utf-8"),
			choice.encode("utf-8"),
		],
		foreign_assets=[gov_asaid],
		rekey_to=None
	)

	try:
		txn_id = txn_register_vote.get_txid()
		algod_client.send_transaction(txn_register_vote.sign(pvk_sender))
		wait_for_confirmation(algod_client, txn_id)
	except Exception as err:
		print(err)

def DAODeclareResult(
	algod_client: algod,
	pvk_sender: str,
	dao_app_id: int64,
	gov_asa_id: int64,
	reg_app_id: int64
	):

	compiled_approval_program = anshelper.compileTeal(anshelper.approval_program(logic.get_application_address(dao_app_id)), Mode.Application,version=6)
	compiled_clear_state_program = anshelper.compileTeal(anshelper.clear_state_program(), Mode.Application,version=6)

	ans_app_program = anshelper.compile_program(algod_client, str.encode(compiled_approval_program))
	ans_clear_program = anshelper.compile_program(algod_client, str.encode(compiled_clear_state_program))

	
	txn_declare_result = transaction.ApplicationNoOpTxn(
		sender=account.address_from_private_key(pvk_sender),
		sp=algod_client.suggested_params(),
		index=dao_app_id,
		foreign_apps= [reg_app_id],
		app_args=[
			"declare_result".encode("utf-8"),
			ans_app_program,
			ans_clear_program
		],
		foreign_assets=[gov_asa_id]
	)

	try:
		txnid = txn_declare_result.get_txid()
		algod_client.send_transaction(txn_declare_result.sign(pvk_sender))
		wait_for_confirmation(algod_client, txnid)
	except Exception as err:
		print(err)



# helper function to compile program source
def compile_program(algod_client: algod, source_code: str) :
	compile_response = algod_client.compile(source_code.decode('utf-8'))
	return base64.b64decode(compile_response['result'])

def import_teal_source_code_as_binary(file_name):
	with open(file_name, 'r') as f:
		data = f.read()
		return str.encode(data)

# helper function that waits for a given txid to be confirmed by the network
def wait_for_confirmation(algod_client,txid) :
	last_round = algod_client.status().get('last-round')
	txinfo = algod_client.pending_transaction_info(txid)
	while not (txinfo.get('confirmed-round') and txinfo.get('confirmed-round') > 0):
		print("Waiting for txn confirmation...")
		last_round += 1
		algod_client.status_after_block(last_round)
		txinfo = algod_client.pending_transaction_info(txid)
	#print("Transaction {} confirmed in round {}.".format(txid, txinfo.get('confirmed-round')))
	print("Txn confirmed in round {}".format(txinfo.get('confirmed-round')))
	return txinfo


class Env(object):

	def __init__(self, algod_client):
		super().__init__()

		self._my_algod_client = algod_client
		self._funding_addr, self._funding_acct_mnemonic = GetFundingAccount(self.my_algod_client)

		print("Deploying ANS Token")
		self._GOV_ASA_ID = DeployANSToken(self.my_algod_client, self._funding_acct_mnemonic)
		print("Deployed ANS Token with Asset-id "+str(self._GOV_ASA_ID))
	
		print("Deploying DAO APP")
		self._DAO_APP_ID=DeployANSDAO(self.my_algod_client, 200000, 1, self._funding_acct_mnemonic,self._GOV_ASA_ID)
		print("Deployed ANS DAO APP with APP-id "+str(self._DAO_APP_ID))
	
		acct_dao_escrow = logic.get_application_address(self._DAO_APP_ID)
		print("DAO Escrow add: "+acct_dao_escrow)
		print("--------------------------------------------------------------------")
		
		print("Funding DAO APP's escrow account: ")
		FundNewAccount(self.my_algod_client, acct_dao_escrow, 1000000, self._funding_acct_mnemonic)
		print("Successfully funded DAO APP's escrow account with 1 ALGO")
		print("--------------------------------------------------------------------")
	
		print("Attemping DAO APP to opt in to GOV ASA")
		DAOOptInToGOVASA(self.my_algod_client, mnemonic.to_private_key(self._funding_acct_mnemonic), self._GOV_ASA_ID, self._DAO_APP_ID)
		print("Successfully opted DAO APP in to GOV ASA")
		print("--------------------------------------------------------------------")
		
	
	@property
	def my_algod_client(self):
		return self._my_algod_client

	@property
	def gov_asa_id(self):
		return self._GOV_ASA_ID
	
	@property
	def funding_addr(self):
		return self._funding_addr
	
	@property
	def funding_acct_mnemonic(self):
		return self._funding_acct_mnemonic

	@property
	def dao_app_id(self):
		return self._DAO_APP_ID

def AddRandomVotesFromRandomAccounts(env: Env, num: int64):

	print("Generating {} random accounts".format(num))

	generated_accts = []
	choices_vote = ["yes", "no", "abstain"]
	privkey_funding_acc = mnemonic.to_private_key(env.funding_acct_mnemonic)

	for i in range(num):
		addr_new_acc, mnem_new_acc = GenerateAccount()
		privkey_new_acc = mnemonic.to_private_key(mnem_new_acc)
		FundNewAccount(env.my_algod_client, addr_new_acc, 1030000, env.funding_acct_mnemonic)
		ASAOptIn(env.my_algod_client, privkey_new_acc, env.gov_asa_id)
		TransferASA(env.my_algod_client, 200000, privkey_funding_acc, addr_new_acc, env.gov_asa_id)
		#DAORegisterVote(env.my_algod_client, random.choice(choices_vote), privkey_new_acc, env.gov_asa_id, env.dao_app_id)
		DAORegisterVote(env.my_algod_client, "yes", privkey_new_acc, env.gov_asa_id, env.dao_app_id)
		generated_accts.append(privkey_new_acc)
	
	return generated_accts

def TestSocialProposal(env: Env):

	new_acct_addr, new_acct_mnemonic = GenerateAccount()
	pvk_funding_acct = mnemonic.to_private_key(env.funding_acct_mnemonic)
	pvk_new_acct = mnemonic.to_private_key(new_acct_mnemonic)

	print("Generated new account: "+new_acct_addr)
	FundNewAccount(env.my_algod_client, new_acct_addr, 2000000, env.funding_acct_mnemonic)
	print("Funded new account {} with 1 ALGO and new balance is: {:,} ALGOs".format(new_acct_addr,util.microalgos_to_algos(env.my_algod_client.account_info(new_acct_addr).get('amount'))))
	
	print("--------------------------------------------------------------------")

	ASAOptIn(env.my_algod_client, pvk_new_acct, env.gov_asa_id)
	print("New account opted in to the GOV ASA")
	print("--------------------------------------------------------------------")

	print("Attempting to transfer 200k ANS to new account")
	TransferASA(env.my_algod_client,20001000,pvk_funding_acct,new_acct_addr,env.gov_asa_id)
	print("Funded new account "+new_acct_addr+"with 200k ANS and new balance is: ")
	print_asset_holding(env.my_algod_client,new_acct_addr, env._GOV_ASA_ID)
	print("--------------------------------------------------------------------")

	#DAO_APP_ID=86039171
	print("Attempting to add a social proposal")
	DAOAddProposalSocial(env.my_algod_client,pvk_new_acct, 1, env.gov_asa_id, 20000000, env.dao_app_id)
	print_asset_holding(env.my_algod_client, new_acct_addr, env.gov_asa_id)
	print("Successfully added social proposal")
	print("--------------------------------------------------------------------")

	print("Funding acct with some more ALGOs to meet raised min balance")
	print("Attempting to vote on the social proposal")
	DAORegisterVote(env.my_algod_client, "yes", pvk_new_acct, env.gov_asa_id, env.dao_app_id)
	print("Successfully registered vote")
	print("--------------------------------------------------------------------")

	AddRandomVotesFromRandomAccounts(env, 2)
	#time.sleep(100)

	print("Declaring Result")
	DAODeclareResult(env.my_algod_client, pvk_new_acct, env.dao_app_id, env.gov_asa_id, 812342)
	print("Vote Declared successfully")
	print("--------------------------------------------------------------------")

def TestFundingProposal(env: Env):

	new_acct_addr, new_acct_mnemonic = GenerateAccount()
	pvk_funding_acct = mnemonic.to_private_key(env.funding_acct_mnemonic)
	pvk_new_acct = mnemonic.to_private_key(new_acct_mnemonic)

	print("Generated new account: "+new_acct_addr)
	funding_amt = 2000000
	FundNewAccount(env.my_algod_client, new_acct_addr, funding_amt, env.funding_acct_mnemonic)
	print("Funded new account {} with {} ALGO and new balance is: {}".format(
		new_acct_addr,
		util.microalgos_to_algos(funding_amt),
		str(env.my_algod_client.account_info(new_acct_addr).get('amount')))
	)
	
	print("--------------------------------------------------------------------")

	ASAOptIn(env.my_algod_client, pvk_new_acct, env.gov_asa_id)
	print("New account opted in to the GOV ASA")
	print("--------------------------------------------------------------------")

	print("Attempting to transfer 200k ANS to new account")
	TransferASA(env.my_algod_client,20001000,pvk_funding_acct,new_acct_addr,env.gov_asa_id)
	print("Funded new account "+new_acct_addr+"with 200k ANS and new balance is: ")
	print_asset_holding(env.my_algod_client,new_acct_addr, env._GOV_ASA_ID)
	print("--------------------------------------------------------------------")


	print("Attempting to Deploy ANS Dot algo registry")
	dot_algo_reg_app_id = anshelper.DeployDotAlgoReg(
		ans_dao_env.my_algod_client, 
		ans_dao_env.funding_acct_mnemonic,
		logic.get_application_address(env.dao_app_id)
	)
	print("Successfully deployed ANS Dot Algo Registry at app-id: {}".format(dot_algo_reg_app_id))
	print("--------------------------------------------------------------------")

	print("Funding Dot Algo Name registry with ALGOs")
	funding_amt = 2000000
	FundNewAccount(env.my_algod_client, logic.get_application_address(dot_algo_reg_app_id), funding_amt, env.funding_acct_mnemonic)
	print("Funded new account {} with {} ALGO and new balance is: {}".format(
		new_acct_addr,
		funding_amt,
		str(env.my_algod_client.account_info(new_acct_addr).get('amount')))
	)
	print("Funding DAO Treasury with ANS")
	funding_amt = 200000
	TransferASA(env.my_algod_client,funding_amt,pvk_funding_acct,logic.get_application_address(env.dao_app_id),env.gov_asa_id)
	print_asset_holding(env.my_algod_client, logic.get_application_address(env.dao_app_id), env.gov_asa_id)
	print("--------------------------------------------------------------------")
	#DAO_APP_ID=86039171
	print("Attempting to add a Funding proposal")
	DAOAddProposalFunding(
		env.my_algod_client,
		pvk_new_acct,
		1, 
		env.gov_asa_id,
		20000000,
		env.dao_app_id,
		dot_algo_reg_app_id,
		100000,
		100000,
		new_acct_addr
	)
	print_asset_holding(env.my_algod_client, new_acct_addr, env.gov_asa_id)
	print("Successfully added funding proposal")
	print("--------------------------------------------------------------------")

	print("Attempting to vote on the funding proposal")
	DAORegisterVote(env.my_algod_client, "yes", pvk_new_acct, env.gov_asa_id, env.dao_app_id)
	print("Successfully registered vote")
	print("--------------------------------------------------------------------")

	AddRandomVotesFromRandomAccounts(env, 1)
	#time.sleep(100)
	
	print("Declaring Result")
	DAODeclareResult(env.my_algod_client, pvk_new_acct, env.dao_app_id, env.gov_asa_id, dot_algo_reg_app_id)
	print("Vote Declared successfully")
	print("--------------------------------------------------------------------")

def TestUpdateRegProposal(env: Env):

	new_acct_addr, new_acct_mnemonic = GenerateAccount()
	pvk_funding_acct = mnemonic.to_private_key(env.funding_acct_mnemonic)
	pvk_new_acct = mnemonic.to_private_key(new_acct_mnemonic)

	print("Generated new account: "+new_acct_addr)
	funding_amt = 2000000
	FundNewAccount(env.my_algod_client, new_acct_addr, funding_amt, env.funding_acct_mnemonic)
	print("Funded new account {} with {} ALGO and new balance is: {}".format(
		new_acct_addr,
		funding_amt,
		str(env.my_algod_client.account_info(new_acct_addr).get('amount')))
	)
	print("--------------------------------------------------------------------")
	print("\n Attempting to make the smart contract opt-in to GOV ASA")
	ASAOptIn(env.my_algod_client, pvk_new_acct, env.gov_asa_id)
	print("New account opted in to the GOV ASA")
	print("--------------------------------------------------------------------")

	print("Attempting to transfer 200k ANS to new account")
	TransferASA(env.my_algod_client,20001000,pvk_funding_acct,new_acct_addr,env.gov_asa_id)
	print("Funded new account "+new_acct_addr+"with 200k ANS and new balance is: ")
	print_asset_holding(env.my_algod_client,new_acct_addr, env._GOV_ASA_ID)
	print("--------------------------------------------------------------------")


	print("Attempting to Deploy ANS Dot algo registry")
	dot_algo_reg_app_id = anshelper.DeployDotAlgoReg(
		ans_dao_env.my_algod_client, 
		ans_dao_env.funding_acct_mnemonic,
		logic.get_application_address(env.dao_app_id)
	)
	print("Successfully deployed ANS Dot Algo Registry at app-id: {}".format(dot_algo_reg_app_id))
	print("--------------------------------------------------------------------")

	funding_amt = 2000000
	print("Funding Dot Algo Name registry with {:,} ALGOs".format(util.microalgos_to_algos(funding_amt)))
	FundNewAccount(env.my_algod_client, logic.get_application_address(dot_algo_reg_app_id), funding_amt, env.funding_acct_mnemonic)
	print("Funded new account {} with {} ALGO and new balance is: {}".format(
		new_acct_addr,
		funding_amt,
		str(env.my_algod_client.account_info(new_acct_addr).get('amount')))
	)
	print("Funding DAO Treasury with ANS")
	funding_amt = 200000
	TransferASA(env.my_algod_client,funding_amt,pvk_funding_acct,logic.get_application_address(env.dao_app_id),env.gov_asa_id)
	print_asset_holding(env.my_algod_client, logic.get_application_address(env.dao_app_id), env.gov_asa_id)
	print("--------------------------------------------------------------------")
	#DAO_APP_ID=86039171
	'''
	print("Attempting to add an Update Registry proposal")
	DAOAddProposalUpdateReg(
		env.my_algod_client,
		pvk_new_acct,
		1, 
		env.gov_asa_id,
		20000000,
		env.dao_app_id,
		dot_algo_reg_app_id,
		new_acct_addr
	)
	print_asset_holding(env.my_algod_client, new_acct_addr, env.gov_asa_id)
	print("Successfully added update registry proposal")
	print("--------------------------------------------------------------------")

	print("Attempting to vote on the update reg proposal")
	DAORegisterVote(env.my_algod_client, "yes", pvk_new_acct, env.gov_asa_id, env.dao_app_id)
	print("Successfully registered vote")
	print("--------------------------------------------------------------------")

	#AddRandomVotesFromRandomAccounts(env, 1)
	#time.sleep(100)
	
	print("Declaring Result")
	DAODeclareResult(env.my_algod_client, pvk_new_acct, env.dao_app_id, env.gov_asa_id, dot_algo_reg_app_id)
	print("Vote Declared successfully")
	print("--------------------------------------------------------------------")
	'''

if __name__ == "__main__":
	ans_dao_env = Env(SetupClient("purestake"))

	#TestSocialProposal(ans_dao_env)

	#TestFundingProposal(ans_dao_env)	

	TestUpdateRegProposal(ans_dao_env)	