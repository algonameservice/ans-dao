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
		self._DAO_APP_ID = DeployANSDAO(self.my_algod_client, 200000, 1, self._funding_acct_mnemonic,self._GOV_ASA_ID)
		print("Deployed ANS DAO APP with APP-id "+str(self._DAO_APP_ID))
	
		acct_dao_escrow = logic.get_application_address(self._DAO_APP_ID)
		print("DAO Escrow add: "+acct_dao_escrow)
		print("--------------------------------------------------------------------")
		
		print("Funding DAO APP's escrow account: ")
		FundNewAccount(self.my_algod_client, acct_dao_escrow, 5000000, self._funding_acct_mnemonic)
		print("Successfully funded DAO APP's escrow account with 1 ALGO")
		print("--------------------------------------------------------------------")
	
		print("Attemping DAO APP to opt in to GOV ASA")
		DAOOptInToGOVASA(self.my_algod_client, mnemonic.to_private_key(self._funding_acct_mnemonic), self._GOV_ASA_ID, self._DAO_APP_ID)
		print("Successfully opted DAO APP in to GOV ASA")
		print("--------------------------------------------------------------------")
		TransferASA(self.my_algod_client,20001000,mnemonic.to_private_key(self.funding_acct_mnemonic),logic.get_application_address(self._DAO_APP_ID),self._GOV_ASA_ID)
	
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
	second_acct_addr, second_acct_mnemonic = GenerateAccount()
	pvk_funding_acct = mnemonic.to_private_key(env.funding_acct_mnemonic)
	pvk_new_acct = mnemonic.to_private_key(new_acct_mnemonic)
	second_acct = mnemonic.to_private_key(second_acct_mnemonic)

	print("Generated new account: "+new_acct_addr)
	FundNewAccount(env.my_algod_client, new_acct_addr, 9000000, env.funding_acct_mnemonic)
	print("Funded new account {} with 9 ALGO and new balance is: {:,} ALGOs".format(new_acct_addr,util.microalgos_to_algos(env.my_algod_client.account_info(new_acct_addr).get('amount'))))
	
	FundNewAccount(env.my_algod_client, second_acct_addr, 2000000, env.funding_acct_mnemonic)
	print("Funded second account {} with 2 ALGO and new balance is: {:,} ALGOs".format(new_acct_addr,util.microalgos_to_algos(env.my_algod_client.account_info(second_acct_addr).get('amount'))))
	print("--------------------------------------------------------------------")

	ASAOptIn(env.my_algod_client, pvk_new_acct, env.gov_asa_id)
	print("New account opted in to the GOV ASA")
	print("--------------------------------------------------------------------")
	
	ASAOptIn(env.my_algod_client, second_acct, env.gov_asa_id)
	print("Second account opted in to the GOV ASA")
	print("--------------------------------------------------------------------")

	print("Attempting to transfer 200k ANS to new account")
	TransferASA(env.my_algod_client,20002000,pvk_funding_acct,new_acct_addr,env.gov_asa_id)
	
	print("Attempting to transfer 200k ANS to second account")
	TransferASA(env.my_algod_client,20002000,pvk_funding_acct,second_acct_addr,env.gov_asa_id)
	
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

	print("Attempting to register a domain")
	gtx_unsign_regname, lsig =  anshelper.prep_name_reg_gtxn(new_acct_addr, "lalith" , 1, dot_algo_reg_app_id, ans_dao_env.my_algod_client)
	anshelper.sign_name_reg_gtxn(new_acct_addr, pvk_new_acct, gtx_unsign_regname, lsig, ans_dao_env.my_algod_client)
	print("Successfully registered a domain")

	print("Attempting to add a social proposal")
	DAOAddProposalSocial(env.my_algod_client,pvk_new_acct, 1, env.gov_asa_id, 20000000, env.dao_app_id, dot_algo_reg_app_id)
	print_asset_holding(env.my_algod_client, new_acct_addr, env.gov_asa_id)
	print("Successfully added social proposal")
	print("--------------------------------------------------------------------")

	print("First account opting in to DAO Dao")
	DappOptIn(env.my_algod_client, pvk_new_acct, env.dao_app_id)
	DappOptIn(env.my_algod_client, pvk_new_acct, get_rewards_app(env.dao_app_id))

	print("Second account opting into both DApps")
	DappOptIn(env.my_algod_client, second_acct, env.dao_app_id)
	DappOptIn(env.my_algod_client, second_acct, get_rewards_app(env.dao_app_id))
	
	print("Delegating vote")
	delegate_vote(env.my_algod_client, pvk_new_acct, second_acct_addr, 1000, env.gov_asa_id, env.dao_app_id, dot_algo_reg_app_id, "lalith")
	#undo_delegate(env.my_algod_client, pvk_new_acct, second_acct_addr, env.gov_asa_id, env.dao_app_id)

	print("Voting as delegate")
	VoteAsDelegate(env.my_algod_client, "yes", second_acct, env.dao_app_id, dot_algo_reg_app_id)
	print("Successfully voted as delegate")
	
	print("Funding acct with some more ALGOs to meet raised min balance")
	'''
	print("Attempting to vote on the social proposal")
	DAORegisterVote(env.my_algod_client, "yes", pvk_new_acct, env.gov_asa_id, env.dao_app_id, dot_algo_reg_app_id, "lalith")
	print("Successfully registered vote")
	print("--------------------------------------------------------------------")
	'''
	#AddRandomVotesFromRandomAccounts(env, 2)
	#time.sleep(100)
	print("Collecting rewards for voting")
	DAOCollectRewards(env.my_algod_client, pvk_new_acct, env.gov_asa_id, env.dao_app_id)

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
	funding_amt = 9000000
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

	print("Attempting to transfer 400k ANS to new account")
	TransferASA(env.my_algod_client,40001000,pvk_funding_acct,new_acct_addr,env.gov_asa_id)
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
	
	print("Attempting to register a domain")
	gtx_unsign_regname, lsig =  anshelper.prep_name_reg_gtxn(new_acct_addr, "lalith" , 1, dot_algo_reg_app_id, ans_dao_env.my_algod_client)
	anshelper.sign_name_reg_gtxn(new_acct_addr, pvk_new_acct, gtx_unsign_regname, lsig, ans_dao_env.my_algod_client)
	print("Successfully registered a domain")

	print("Funding DAO Treasury with ANS")
	funding_amt = 200000
	TransferASA(env.my_algod_client,funding_amt,pvk_funding_acct,logic.get_application_address(env.dao_app_id),env.gov_asa_id)
	print_asset_holding(env.my_algod_client, logic.get_application_address(env.dao_app_id), env.gov_asa_id)
	print("--------------------------------------------------------------------")
	#DAO_APP_ID=86039171
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
	DAORegisterVote(env.my_algod_client, "yes", pvk_new_acct, env.gov_asa_id, env.dao_app_id, dot_algo_reg_app_id, "lalith")
	print("Successfully registered vote")
	print("--------------------------------------------------------------------")

	#AddRandomVotesFromRandomAccounts(env, 1)
	#time.sleep(100)

	print("Declaring Result")
	DAODeclareResult(env.my_algod_client, pvk_new_acct, env.dao_app_id, env.gov_asa_id, dot_algo_reg_app_id)
	print("Vote Declared successfully")
	print("--------------------------------------------------------------------")

def TestDaoUpdateProposal(env: Env):

	new_acct_addr, new_acct_mnemonic = GenerateAccount()
	pvk_funding_acct = mnemonic.to_private_key(env.funding_acct_mnemonic)
	pvk_new_acct = mnemonic.to_private_key(new_acct_mnemonic)

	print("Generated new account: "+new_acct_addr)
	funding_amt = 9000000
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
	TransferASA(env.my_algod_client,40001000,pvk_funding_acct,new_acct_addr,env.gov_asa_id)
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
	
	print("Attempting to register a domain")
	gtx_unsign_regname, lsig =  anshelper.prep_name_reg_gtxn(new_acct_addr, "lalith" , 1, dot_algo_reg_app_id, ans_dao_env.my_algod_client)
	anshelper.sign_name_reg_gtxn(new_acct_addr, pvk_new_acct, gtx_unsign_regname, lsig, ans_dao_env.my_algod_client)
	print("Successfully registered a domain")

	print("Funding DAO Treasury with ANS")
	funding_amt = 200000
	TransferASA(env.my_algod_client,funding_amt,pvk_funding_acct,logic.get_application_address(env.dao_app_id),env.gov_asa_id)
	print_asset_holding(env.my_algod_client, logic.get_application_address(env.dao_app_id), env.gov_asa_id)
	print("--------------------------------------------------------------------")
	#DAO_APP_ID=86039171
	print("Attempting to add an DAO Update proposal")
	DAOAddUpdateProposal(
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
	print("Successfully added DAO update proposal")
	print("--------------------------------------------------------------------")
	
	print("Attempting to vote on the dao update proposal")
	DAORegisterVote(env.my_algod_client, "yes", pvk_new_acct, env.gov_asa_id, env.dao_app_id, dot_algo_reg_app_id, "lalith")
	print("Successfully registered vote")
	print("--------------------------------------------------------------------")

	print("Declaring Result")
	DAODeclareUpdateRegResult(env.my_algod_client, pvk_new_acct, env.dao_app_id, env.gov_asa_id, dot_algo_reg_app_id)
	print("Vote Declared successfully")
	print("--------------------------------------------------------------------")
	

if __name__ == "__main__":

	ans_dao_env = Env(SetupClient("purestake"))

	#TestDaoUpdateProposal(ans_dao_env)

	TestSocialProposal(ans_dao_env)

	#TestFundingProposal(ans_dao_env)	

	#TestUpdateRegProposal(ans_dao_env)