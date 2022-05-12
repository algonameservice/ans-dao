# Algorand Name Service DAO

The ANS DAO is a Decentralized Autonomous Organization on the Algorand network that governs the Algorand Name Service treasury and name policy.

The smart contracts in this repo have been forked from [Algobuilder's DAO template](https://github.com/scale-it/algo-builder/tree/master/examples/dao).


Voting power is TBD and is currently defined by ASA holding (1 ASA = 1 voting power): each token holder is a DAO member and can participate equally in the governance.


## Global parameters:

-  `deposit` — _200k $ANS_ — deposit amount in `$ANS` required to make a proposal

-  `min_support` — _20k $ANS_ — a minimum number of `yes` power votes (other votes like `abstain` and `no` are not counted) to validate the proposal

-  `min_duration` — _7 days_ — minimum voting time (in number of seconds) for a new proposal

-  `max_duration` — _10 days_ — maximum voting time (in number of seconds) for a new proposal

-  `url` — [ANS Governance Docs]() — a link with more information about the DAO

## Proposals:

### General conditions

* Only 1 proposal of any type can be active at once
* Cooldown period is applied equaling half the duration of previous vote

## Types of Proposals:

* `Social:` This type of proposal calls for an action off-chain that can be executed by the team of directors. This type of proposal does not mobilize any funds from treasury nor does it make a change to the registry smart contract.

	The _social_ proposal requires the following basic parameters common to all proposals:
	* duration (in number of blocks): to determine the duration of the vote
	* url (of the proposal): discourse or GitHub url to the proposal

	Upon completion of vote, the `social` proposal does not perform any action. The vote results are recorded for posterity and the staked tokens are returned to the owner.

* `Funding:` This type of proposal mobilizes funds from the treasury.

	The following additional _input parameters_ are required:
	* recipient_address (Algorand account in string): Valid Algorand address of recipient
	* amount_algos (number of $ALGO requested): Amount requested in ALGOs
	* amount_ans (number of $ANS requested): Amount requested in ANS tokens

	The following conditions apply:
	* Only 20% of registry treasury ($ALGO) can be requested at once
	* Only 20% of ANS token treasury ($ANS) can be requested at once

	This proposal will perform the following additional actions if it passes:
	* Withdraw ALGOs from the registry treasury and deposit it into recipent's address
	* Deposit ANS tokens from DAO treasury into the recipient's address

* `Update Registry:` This type of proposal calls for a change in the registry smart contract or for an action from the current directors. This proposal does not mobilize funds.

	The following additional parameters are required for the Update Registry proposal:
	* registry_app_id (integer): Must be valid APP_ID of the name registry
	* approval_program (bytecode): registry's updated approval program
	* app_args (string list): the application arguments corresponding to the approval program and registry's update method

	This proposal will prepare and execute InnerTransaction that calls the registry smart contract's update method.

## Run tests
Install required python packages
```
pip3 install -r requirements.txt
```
Run tests
```
cd my-tests
python3 TestANSDAO.py
```
