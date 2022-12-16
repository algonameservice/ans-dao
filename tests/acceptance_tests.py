from cgi import test
from ans_dao_helper import *
from numpy import int64

#TODO: Convert to real unit tests

import unittest

class Env(object):

	def __init__(self, algod_client):
		super().__init__()

		self._my_algod_client = algod_client
		self._funding_addr, self._funding_acct_mnemonic = GetFundingAccount(self.my_algod_client)
		
		print("Deploying DAO APP")
		self._GOV_ASA_ID = DeployANSToken(self.my_algod_client, self.funding_acct_mnemonic)
		
		print("Attempting to Deploy ANS Dot algo registry")
		dot_algo_reg_app_id = anshelper.DeployDotAlgoReg(
			algod_client, 
			self.funding_acct_mnemonic
		)

		self.REGISTRY_DAPP_ID = dot_algo_reg_app_id

		print("Successfully deployed ANS Dot Algo Registry at app-id: {}".format(dot_algo_reg_app_id))
		
		self._DAO_APP_ID = DeployANSDAO(self.my_algod_client, 200000, 1, self._funding_acct_mnemonic,self._GOV_ASA_ID, dot_algo_reg_app_id)
		print(self._DAO_APP_ID)

		print("Deployed ANS DAO APP with APP-id "+str(self._DAO_APP_ID))
		
		acct_dao_escrow = logic.get_application_address(self._DAO_APP_ID)
		print("DAO Escrow add: "+acct_dao_escrow)
		print("--------------------------------------------------------------------")

		print('Updating global state of Registry Dapp')

		anshelper.update_global_state(self.my_algod_client, acct_dao_escrow, self._DAO_APP_ID, dot_algo_reg_app_id, self.funding_acct_mnemonic)
		
		print('Global state updated')
		
		print("Funding DAO APP's escrow account: ")
		FundNewAccount(self.my_algod_client, acct_dao_escrow, 8000000, self._funding_acct_mnemonic)
		print("Successfully funded DAO APP's escrow account with 1 ALGO")
		print("--------------------------------------------------------------------")
	
		print("Attemping DAO APP to opt in to GOV ASA")
		DAOOptInToGOVASA(self.my_algod_client, mnemonic.to_private_key(self._funding_acct_mnemonic), self._GOV_ASA_ID, self._DAO_APP_ID)
		print("Successfully opted DAO APP in to GOV ASA")
		print("--------------------------------------------------------------------")
		TransferASA(self.my_algod_client,20001000,mnemonic.to_private_key(self.funding_acct_mnemonic),logic.get_application_address(self._DAO_APP_ID),self._GOV_ASA_ID)
		
		new_acct_addr, new_acct_mnemonic = GenerateAccount()
		second_acct_addr, second_acct_mnemonic = GenerateAccount()
		pvk_funding_acct = mnemonic.to_private_key(self.funding_acct_mnemonic)
		pvk_new_acct = mnemonic.to_private_key(new_acct_mnemonic)
		print("New Acct Mnemonic")
		print(new_acct_mnemonic)
		second_acct = mnemonic.to_private_key(second_acct_mnemonic)

		self._new_acct_addr = new_acct_addr
		self._new_acct_mnemonic = new_acct_mnemonic
		self._pvk_funding_acct = pvk_funding_acct
		self._pvk_new_acct = pvk_new_acct
		self._second_acct_addr = second_acct_addr
		self._second_acct_mnemonic = second_acct_mnemonic
		self._second_acct = second_acct


		print("Generated new account: "+new_acct_addr)
		FundNewAccount(self.my_algod_client, new_acct_addr, 14000000, self.funding_acct_mnemonic)
		print("Funded new account {} with 9 ALGO and new balance is: {:,} ALGOs".format(new_acct_addr,util.microalgos_to_algos(self.my_algod_client.account_info(new_acct_addr).get('amount'))))
		
		FundNewAccount(self.my_algod_client, second_acct_addr, 4000000, self.funding_acct_mnemonic)
		print("Funded second account {} with 2 ALGO and new balance is: {:,} ALGOs".format(new_acct_addr,util.microalgos_to_algos(self.my_algod_client.account_info(second_acct_addr).get('amount'))))
		print("--------------------------------------------------------------------")

		ASAOptIn(self.my_algod_client, pvk_new_acct, self.gov_asa_id)
		print("New account opted in to the GOV ASA")
		print("--------------------------------------------------------------------")
		
		ASAOptIn(self.my_algod_client, second_acct, self.gov_asa_id)
		print("Second account opted in to the GOV ASA")
		print("--------------------------------------------------------------------")

		print("Attempting to transfer 200k ANS to new account")
		TransferASA(self.my_algod_client,40002000,pvk_funding_acct,new_acct_addr,self.gov_asa_id)
		
		print("Attempting to transfer 200k ANS to second account")
		TransferASA(self.my_algod_client,40002000,pvk_funding_acct,second_acct_addr,self.gov_asa_id)
		
		print("Funded new account "+new_acct_addr+"with 200k ANS and new balance is: ")
		print_asset_holding(self.my_algod_client,new_acct_addr, self._GOV_ASA_ID)
		print("--------------------------------------------------------------------")

		print("Attempting to register a domain")
		gtx_unsign_regname, lsig =  anshelper.prep_name_reg_gtxn(new_acct_addr, "lalith" , 1, dot_algo_reg_app_id, self.my_algod_client)
		anshelper.sign_name_reg_gtxn(new_acct_addr, pvk_new_acct, gtx_unsign_regname, lsig, self.my_algod_client)
		print("Successfully registered a domain")

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
	
	@property
	def dot_algo_reg_app_id(self):
		return self.REGISTRY_DAPP_ID
	
	@property
	def new_acct_addr(self):
		return self._new_acct_addr
	
	@property
	def new_acct_mnemonic(self):
		return self._new_acct_mnemonic
	
	@property
	def pvk_funding_acct(self):
		return self._pvk_funding_acct

	@property
	def pvk_new_acct(self):
		return self._pvk_new_acct

	@property
	def second_acct_addr(self):
		return self._second_acct_addr

	@property
	def second_acct_mnemonic(self):
		return self._second_acct_mnemonic

	@property
	def second_acct(self):
		return self._second_acct

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

	print("Attempting to add a social proposal")
	DAOAddProposalSocial(env.my_algod_client, env.pvk_new_acct, 1, env.gov_asa_id, 20000000, env.dao_app_id, env.dot_algo_reg_app_id)
	print_asset_holding(env.my_algod_client, env.new_acct_addr, env.gov_asa_id)
	print("Successfully added social proposal")
	print("--------------------------------------------------------------------")

	print("First account opting in to DAO Dao")
	DappOptIn(env.my_algod_client, env.pvk_new_acct, env.dao_app_id)
	DappOptIn(env.my_algod_client, env.pvk_new_acct, get_rewards_app(env.dao_app_id))

	print("Second account opting into both DApps")
	DappOptIn(env.my_algod_client, env.second_acct, env.dao_app_id)
	DappOptIn(env.my_algod_client, env.second_acct, get_rewards_app(env.dao_app_id))
	
	#print('accepting to be a delegate')
	#accept_delegate(env.my_algod_client, env.second_acct, env.dao_app_id, env.gov_asa_id)
	#print("Delegating vote")
	#delegate_vote(env.my_algod_client, pvk_new_acct, second_acct_addr, 1000, env.gov_asa_id, env.dao_app_id, env.dot_algo_reg_app_id, "lalith")
	
	#undo_delegate(env.my_algod_client, pvk_new_acct, second_acct_addr, env.gov_asa_id, env.dao_app_id)
	
	#print("Voting as delegate")
	#VoteAsDelegate(env.my_algod_client, "yes", second_acct, env.dao_app_id, env.dot_algo_reg_app_id)
	#print("Successfully voted as delegate")
	
	
	print("Funding acct with some more ALGOs to meet raised min balance")
	
	print("Attempting to vote on the social proposal")
	DAORegisterVote(env.my_algod_client, "yes", env.pvk_new_acct, env.gov_asa_id, env.dao_app_id, env.dot_algo_reg_app_id, "lalith")
	print("Successfully registered vote")
	print("--------------------------------------------------------------------")
	
	#AddRandomVotesFromRandomAccounts(env, 2)
	#time.sleep(100)
	print("Collecting rewards for voting")
	DAOCollectRewards(env.my_algod_client, env.pvk_new_acct, env.gov_asa_id, env.dao_app_id)

	print("Declaring Result")
	DAODeclareResult(env.my_algod_client, env.pvk_new_acct, env.dao_app_id, env.gov_asa_id, 812342)
	print("Vote Declared successfully")
	print("--------------------------------------------------------------------")
	
def TestFundingProposal(env: Env):

	print("Attempting to add a Funding proposal")
	DAOAddProposalFunding(
		env.my_algod_client,
		env.pvk_new_acct,
		1, 
		env.gov_asa_id,
		20000000,
		env.dao_app_id,
		env.dot_algo_reg_app_id,
		100000,
		100000,
		env.new_acct_addr
	)
	print_asset_holding(env.my_algod_client, env.new_acct_addr, env.gov_asa_id)
	print("Successfully added funding proposal")
	print("--------------------------------------------------------------------")

	print("First account opting in to DAO Dao")
	DappOptIn(env.my_algod_client, env.pvk_new_acct, env.dao_app_id)
	DappOptIn(env.my_algod_client, env.pvk_new_acct, get_rewards_app(env.dao_app_id))

	print("Second account opting into both DApps")
	DappOptIn(env.my_algod_client, env.second_acct, env.dao_app_id)
	DappOptIn(env.my_algod_client, env.second_acct, get_rewards_app(env.dao_app_id))

	print('accepting to be a delegate')
	accept_delegate(env.my_algod_client, env.second_acct, env.dao_app_id, env.gov_asa_id)

	print("Delegating vote")
	delegate_vote(env.my_algod_client, env.pvk_new_acct, env.second_acct_addr, 1000, env.gov_asa_id, env.dao_app_id, env.dot_algo_reg_app_id, "lalith")
	#undo_delegate(env.my_algod_client, pvk_new_acct, second_acct_addr, env.gov_asa_id, env.dao_app_id)

	print("Voting as delegate")
	VoteAsDelegate(env.my_algod_client, "yes", env.second_acct, env.dao_app_id, env.dot_algo_reg_app_id)
	print("Successfully voted as delegate")
	
	print("Funding acct with some more ALGOs to meet raised min balance")
	'''
	print("Attempting to vote on the social proposal")
	DAORegisterVote(env.my_algod_client, "yes", pvk_new_acct, env.gov_asa_id, env.dao_app_id, env.dot_algo_reg_app_id, "lalith")
	print("Successfully registered vote")
	print("--------------------------------------------------------------------")
	'''
	#AddRandomVotesFromRandomAccounts(env, 2)
	#time.sleep(100)
	print("Collecting rewards for voting")
	DAOCollectRewards(env.my_algod_client, env.pvk_new_acct, env.gov_asa_id, env.dao_app_id)

	print("Declaring Result")
	DAODeclareResult(env.my_algod_client, env.pvk_new_acct, env.dao_app_id, env.gov_asa_id, 812342)
	print("Vote Declared successfully")
	print("--------------------------------------------------------------------")

def TestUpdateRegProposal(env: Env):

	print("Attempting to add an Update Registry proposal")
	DAOAddProposalUpdateReg(
		env.my_algod_client,
		env.pvk_new_acct,
		1, 
		env.gov_asa_id,
		20000000,
		env.dao_app_id,
		env.dot_algo_reg_app_id,
		env.new_acct_addr
	)
	print_asset_holding(env.my_algod_client, env.new_acct_addr, env.gov_asa_id)
	print("Successfully added update registry proposal")
	print("--------------------------------------------------------------------")

	print("Attempting to vote on the update reg proposal")
	DAORegisterVote(env.my_algod_client, "yes", env.pvk_new_acct, env.gov_asa_id, env.dao_app_id, env.dot_algo_reg_app_id, "lalith")
	print("Successfully registered vote")
	print("--------------------------------------------------------------------")

	print("Declaring Result")
	DAODeclareRegistryUpdateReg(env.my_algod_client, env.pvk_new_acct, env.dao_app_id, env.gov_asa_id, env.dot_algo_reg_app_id)
	print("Vote Declared successfully")
	print("--------------------------------------------------------------------")

def TestDaoUpdateProposal(env: Env):

	print("Attempting to add an DAO Update proposal")
	DAOAddUpdateProposal(
		env.my_algod_client,
		env.pvk_new_acct,
		1, 
		env.gov_asa_id,
		20000000,
		env.dao_app_id,
		env.dot_algo_reg_app_id,
		env.new_acct_addr
	)
	print_asset_holding(env.my_algod_client, env.new_acct_addr, env.gov_asa_id)
	print("Successfully added DAO update proposal")
	print("--------------------------------------------------------------------")
	
	print("Attempting to vote on the dao update proposal")
	DAORegisterVote(env.my_algod_client, "yes", env.pvk_new_acct, env.gov_asa_id, env.dao_app_id, env.dot_algo_reg_app_id, "lalith")
	print("Successfully registered vote")
	print("--------------------------------------------------------------------")

	print("Declaring Result")
	DAODeclareUpdateRegResult(env.my_algod_client, env.pvk_new_acct, env.dao_app_id, env.gov_asa_id, env.dot_algo_reg_app_id)
	print("Vote Declared successfully")
	print("--------------------------------------------------------------------")
	

if __name__ == "__main__":

	ans_dao_env = Env(SetupClient("purestake"))

	#TestSocialProposal(ans_dao_env)
	#TestFundingProposal(ans_dao_env)	
	#TestUpdateRegProposal(ans_dao_env)
	TestDaoUpdateProposal(ans_dao_env)