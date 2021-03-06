from email.parser import BytesParser
import sys
from numpy import byte, uint

from pyteal import *

def approval_program(ARG_GOV_TOKEN):
    """
    A stateful app with governance rules. Stores
    deposit, min_support, min_duration, max_duration, url.

    Commands:
        add_proposal            Save proposal record in lsig
        deposit_vote_token      records deposited votes in voter.account
        register_vote           register user votes in proposal_lsig
        execute                 executes a proposal
        withdraw_vote_deposit   unlock the deposit and withdraw tokens back to the user
        clear_vote_record       clears Sender local state by removing a record of vote cast from a not active proposal
        clear_proposal          clears proposal record and returns back the deposit
    """

    # global DAO parameters
    govtoken_asa_id = Bytes("GOV_TOKEN_ASA_ID")
    deposit = App.globalGet(Bytes("deposit"))
    min_support = App.globalGet(Bytes("min_support"))
    min_duration = App.globalGet(Bytes("min_duration"))
    max_duration = App.globalGet(Bytes("max_duration"))
    url = App.globalGet(Bytes("url"))

    # Proposal params
    bytes_proposal_id = Bytes("proposal_id")
    bytes_proposal_result = Bytes("UNKNOWN") # PASSED, REJECTED
    bytes_proposal_initiator = Bytes("proposal_initiator") # Acct Addr
    bytes_proposal_status = Bytes("proposal_status") # Active, Completed
    bytes_proposal_type = Bytes("proposal_type") # Social/Funding/UpdateReg
    bytes_voting_start = Bytes("voting_start") # Unix Timestamp
    bytes_voting_end = Bytes("voting_end") # Unix Timestamp
    bytes_proposal_url = Bytes("proposal_url") # URI
    bytes_votecount_yes = Bytes("votecount_yes") # No. of yes
    bytes_votecount_no = Bytes("votecount_no") # No. of no
    bytes_votecount_abstain = Bytes("votecount_abstain") # No. of no
    bytes_proposal_funding_amt_algo = Bytes("proposal_funding_amt_algo")
    bytes_proposal_funding_amt_ans = Bytes("proposal_funding_amt_asa")
    bytes_funding_recipient = Bytes("funding_recipient")
    bytes_reg_app_id_to_update = Bytes("reg_app_id_to_update")
    bytes_total_coins_voted = Bytes("total_coins_voted")
    bytes_reg_app_progrm_hash = Bytes("reg_app_progrm_hash") # For ex: 123456
    bytes_reg_clear_progrm_hash = Bytes("reg_clear_progrm_hash") # For ex: 123456
    proposal_id_global = App.globalGet(bytes_proposal_id)

    @Subroutine(TealType.none)
    def ResetProposalParams():
        return Seq([
        App.globalPut(bytes_proposal_initiator,Bytes("NONE")),
        App.globalPut(bytes_proposal_status,Bytes("completed")),
        App.globalPut(bytes_proposal_type,Bytes("NONE")),
        App.globalPut(bytes_voting_start,Int(0)),
        App.globalPut(bytes_voting_end,Int(0)),
        App.globalPut(bytes_proposal_url,Bytes("NONE")),
        App.globalPut(bytes_reg_app_progrm_hash,Bytes("NONE")),
        App.globalPut(bytes_reg_clear_progrm_hash,Bytes("NONE")),
        App.globalPut(bytes_votecount_yes,Int(0)),
        App.globalPut(bytes_votecount_no,Int(0)),
        App.globalPut(bytes_votecount_abstain,Int(0)),
        App.globalPut(bytes_proposal_funding_amt_algo,Int(0)),
        App.globalPut(bytes_proposal_funding_amt_ans,Int(0)),
        App.globalPut(bytes_funding_recipient,Global.zero_address()),
        App.globalPut(bytes_reg_app_id_to_update,Int(0)),
        App.globalPut(bytes_total_coins_voted, Int(0))
    ])

    # initialization
    # Expected arguments:
    #   [deposit, min_support, min_duration, max_duration, url]
    on_initialize = Seq([
        Assert(
            And(
                # min_duration must be > 0
                Btoi(Txn.application_args[2]) > Int(0),
                # min_duration < max_duration
                Btoi(Txn.application_args[2]) < Btoi(Txn.application_args[3]),
            )
        ),
        App.globalPut(Bytes("deposit"), Btoi(Txn.application_args[0])),
        App.globalPut(Bytes("min_support"), Btoi(Txn.application_args[1])),
        App.globalPut(Bytes("min_duration"), Btoi(Txn.application_args[2])),
        App.globalPut(Bytes("max_duration"), Btoi(Txn.application_args[3])),
        App.globalPut(Bytes("url"), Txn.application_args[4]),
        App.globalPut(govtoken_asa_id, Txn.assets[0]), 
        ResetProposalParams(),
        App.globalPut(bytes_proposal_id,Int(31420)),
        Return(Int(1))
    ])

    # This is separate because the smart contract needs minimum balance to send
    # opt in txn
    opt_in_to_gov_token = Seq([
        #TODO: Validate sender and make sure this txn can't be abused
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.asset_receiver: Global.current_application_address(),
            TxnField.asset_amount: Int(0),
            TxnField.xfer_asset: Int(ARG_GOV_TOKEN)
        }),
        InnerTxnBuilder.Submit(),
        Return(Int(1))
    ])

    acct_reg_treasury = ScratchVar(TealType.bytes)
    balance_reg_treasury = ScratchVar(TealType.uint64)
    balance_dao_treasury = ScratchVar(TealType.uint64)
    max_funding_amt_algos = ScratchVar(TealType.uint64)
    max_funding_amt_ans = ScratchVar(TealType.uint64)
    acct_balance_asa = ScratchVar(TealType.uint64)

    @Subroutine(TealType.none)
    def store_app_address():
        return Seq([
            addr := AppParam.address(Int(1)),
            If(addr.hasValue(), 
            acct_reg_treasury.store(addr.value()))
        ])

    @Subroutine(TealType.none)
    def store_balance_reg_treasury(param):
        return Seq(
            balance := AccountParam.balance(param),
            If(balance.hasValue(),
            balance_reg_treasury.store(balance.value()))
        )

    @Subroutine(TealType.none)
    def store_balance_dao_treasury(param):
        return Seq(
            balance := AccountParam.balance(param),
            If(balance.hasValue(),
            balance_dao_treasury.store(balance.value()))
        )               
    
    @Subroutine(TealType.none)
    def store_voters_token_balance(addr_sender, asaid) :
        return Seq(
            balance := AssetHolding.balance(addr_sender, asaid),
            If(balance.hasValue())
            .Then(
                acct_balance_asa.store(balance.value())
            ).Else(
                acct_balance_asa.store(Int(0))
            )
        )
    
    users_last_proposal = ScratchVar(TealType.uint64)
    @Subroutine(TealType.none)
    def get_users_last_proposal():
        return Seq([
            last_proposal := App.localGetEx(Int(0), Int(0), bytes_proposal_id),
            If(last_proposal.hasValue() == Int(1))
            .Then( users_last_proposal.store(last_proposal.value()))
            .Else( users_last_proposal.store(Int(0))),
        ])

    basic_checks_xfer = Seq([
        Assert(
            And(
                Txn.rekey_to() == Global.zero_address(),
                Txn.asset_close_to() == Global.zero_address(),
                TxnField.close_remainder_to == Global.zero_address(),
            )
        )
    ])

    # App-args: 
    # Social - [ type Social , duration (no. of days), url ]
    # Funding - [ type Funding , duration (no. of days), url, amt_algos, amt_ans ];
    #           foreign-accounts = [<funding_recipient>];
    #           foreign-apps = [reg_app_id]
    # UpdateReg - [ type UpdateReg , duration (no. of days), url, reg_app_id, approval_program ]
    add_proposal = Seq([
        # TODO: Uncomment below once vars are initiatilized
        Assert(
            And( 
                App.globalGet(bytes_proposal_status) == Bytes("completed"),
                Global.group_size()==Int(2),
                App.globalGet(bytes_votecount_yes)==Int(0),
                App.globalGet(bytes_votecount_no)==Int(0),
                App.globalGet(bytes_votecount_abstain)==Int(0),
                Btoi(Gtxn[1].application_args[2])<=max_duration,
                Gtxn[0].type_enum() == TxnType.AssetTransfer,
                Gtxn[0].asset_receiver() == Global.current_application_address(),
                Gtxn[0].asset_amount() == deposit,
                Or(
                    Gtxn[1].application_args[1] == Bytes("social"),
                    Gtxn[1].application_args[1] == Bytes("funding"),
                    Gtxn[1].application_args[1] == Bytes("updatereg"),
                )
            )
        ),
        # TODO: do basic checks for txns
        #TODO: do basic checks for url input
        App.globalPut(bytes_proposal_id, Add(proposal_id_global,Int(1))),
        App.globalPut(bytes_proposal_initiator, Gtxn[0].sender()),
        App.globalPut(bytes_proposal_type, Gtxn[1].application_args[1]),
        App.globalPut(Bytes("voting_start"), Global.latest_timestamp()),
        #App.globalPut(Bytes("voting_end"), Add(Global.latest_timestamp(), Mul(Btoi(Gtxn[1].application_args[2]),Int(86400)))),
        App.globalPut(Bytes("voting_end"), Add(Global.latest_timestamp(), Mul(Btoi(Gtxn[1].application_args[2]),Int(60)))),
        App.globalPut(bytes_proposal_url, Gtxn[1].application_args[3]),
        App.globalPut(bytes_proposal_status, Bytes("active")),
        App.globalPut(bytes_proposal_result, Bytes("UNKNOWN")),
        If(Gtxn[1].application_args[1]==Bytes("funding"))
        .Then(
            Seq([ 
                # TODO: Check maybe value
                store_balance_reg_treasury(Txn.accounts[2]),
                max_funding_amt_algos.store(Div(balance_reg_treasury.load(),Int(5))),
                store_balance_dao_treasury(Global.current_application_address()),
                max_funding_amt_ans.store(Div(balance_dao_treasury.load(),Int(5))),
                Assert(
                    And(
                        Btoi(Gtxn[1].application_args[4])>=Int(0),
                        Btoi(Gtxn[1].application_args[4])<=max_funding_amt_algos.load()
                    )
                ),
                App.globalPut(bytes_proposal_funding_amt_algo, Btoi(Gtxn[1].application_args[4])),
                Assert(
                    And(
                        Btoi(Gtxn[1].application_args[5])>=Int(0),
                        Btoi(Gtxn[1].application_args[5])<=max_funding_amt_ans.load()
                    )
                ),
                App.globalPut(bytes_reg_app_id_to_update,Txn.applications[1]),
                App.globalPut(bytes_proposal_funding_amt_ans, Btoi(Gtxn[1].application_args[5])),
                App.globalPut(bytes_funding_recipient, Gtxn[1].accounts[1])
        ])
        ).ElseIf(Gtxn[1].application_args[1]==Bytes("updatereg"))
        .Then(
            Seq( 
                # TODO: Confirm the app_id is valid within reason
                App.globalPut(bytes_reg_app_id_to_update, Btoi(Gtxn[1].application_args[4])),
                App.globalPut(bytes_reg_app_progrm_hash, Sha512_256(Txn.application_args[5])),
                App.globalPut(bytes_reg_clear_progrm_hash, Sha512_256(Txn.application_args[6]))
            )
        ),
        Return(Int(1))
    ])

    bytes_yes = Bytes("yes")
    bytes_no = Bytes("no")
    bytes_abstain = Bytes("abstain")
    bytes_hasvoted = Bytes("has_voted")
    bytes_voteresponse = Bytes("vote_response")

    on_register = Seq([
        App.localPut(Int(0), bytes_proposal_id, Int(0)),
        App.localPut(Int(0), bytes_voteresponse, Bytes("UNKNOWN")),
        App.localPut(Int(0), bytes_hasvoted, Bytes("NO")),
        Return(Int(1))
    ])


    # Register vote:
    #   apps-args: ["vote", <yes/no/abstain>]
    #   foreign-assets: [<gov_token_asa_id>]
    vote = Seq([
        store_voters_token_balance(Txn.sender(),App.globalGet(govtoken_asa_id)),
        get_users_last_proposal(),
        Assert(
            And(
                App.optedIn(Txn.sender(),App.id()),
                # voting_start <= now <= voting_end
                App.globalGet(bytes_voting_start) <= Global.latest_timestamp(),
                Global.latest_timestamp() <= App.globalGet(bytes_voting_end),
                Txn.assets[0]==App.globalGet(govtoken_asa_id),
                acct_balance_asa.load()>=Int(0),
                # Sender.deposit >= 0 (i.e user "deposited" his votes using deposit_vote_token)
                Or(
                    users_last_proposal.load() == Int(0),
                    users_last_proposal.load() != proposal_id_global
                )
            )
        ),
        If(Txn.application_args[1]==bytes_yes)
        .Then(
            App.globalPut(bytes_votecount_yes, Add(App.globalGet(bytes_votecount_yes),Int(1)))
        ).ElseIf(Txn.application_args[1]==bytes_no)
        .Then(
            App.globalPut(bytes_votecount_no, Add(App.globalGet(bytes_votecount_no),Int(1)))
        ).ElseIf(Txn.application_args[1]==bytes_abstain)
        .Then(
            App.globalPut(bytes_votecount_abstain, Add(App.globalGet(bytes_votecount_abstain),Int(1)))
        ).Else(
            Err()
        ),
        App.globalPut(bytes_total_coins_voted, Add(App.globalGet(bytes_total_coins_voted), acct_balance_asa.load())),
        Return(Int(1))
    ])

    return_deposit = Seq([
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.asset_receiver: App.globalGet(bytes_proposal_initiator),
            TxnField.asset_amount: App.globalGet(Bytes("deposit")),
            TxnField.xfer_asset: Txn.assets[0]
        }),
        InnerTxnBuilder.Submit()
    ])

    scratchvar_prpsl_funding_amt = ScratchVar(TealType.bytes)

    @Subroutine(TealType.none)
    def get_prpsl_fund_amt():
        return Seq([
            scratchvar_prpsl_funding_amt.store(Itob(App.globalGet(bytes_proposal_funding_amt_algo)))
        ])

    withdraw_funds_from_name_registry = Seq([
        #TODO: Assert(Txn.applications[1]==App.globalGet(bytes_reg_app_id_to_update)),
        get_prpsl_fund_amt(),
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.ApplicationCall,
            TxnField.application_id: Txn.applications[1],
            TxnField.accounts: [App.globalGet(bytes_funding_recipient)],
            TxnField.on_completion: OnComplete.NoOp,
            TxnField.application_args: [ Bytes("withdraw_funds"), scratchvar_prpsl_funding_amt.load()]
        }),
        InnerTxnBuilder.Submit()
    ])


    update_registry_approval_program = Seq([
        #TODO: make these assertions work
        Assert(App.globalGet(bytes_reg_app_progrm_hash) == Sha512_256(Txn.application_args[1])),
        Assert(App.globalGet(bytes_reg_clear_progrm_hash) == Sha512_256(Txn.application_args[2])),
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.ApplicationCall,
            TxnField.application_id: Txn.applications[1],
            TxnField.on_completion: OnComplete.UpdateApplication,
            TxnField.approval_program: Txn.application_args[1],
            TxnField.clear_state_program: Txn.application_args[2]
        }),
        InnerTxnBuilder.Submit()
    ])


    withdraw_funds_from_dao_treasury = Seq([
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.asset_receiver: App.globalGet(bytes_proposal_initiator),
            TxnField.asset_amount: App.globalGet(bytes_proposal_funding_amt_ans),
            TxnField.xfer_asset: Txn.assets[0]
        }),
        InnerTxnBuilder.Submit()
    ])

    @Subroutine(TealType.uint64)
    def DidVotePass():
        return And(
            App.globalGet(bytes_votecount_yes)>App.globalGet(bytes_votecount_no),
            App.globalGet(bytes_votecount_yes)>App.globalGet(bytes_votecount_abstain),
            App.globalGet(bytes_total_coins_voted) >= App.globalGet(Bytes("min_support"))
        )

    declare_result = Seq([
        Assert(
            And(
                Global.latest_timestamp()>=App.globalGet(bytes_voting_end),
                App.globalGet(bytes_proposal_status)==Bytes("active"),
                Txn.assets[0] == App.globalGet(govtoken_asa_id)
                # TODO: Add any more checks necessary here
            )
        ),
        If(DidVotePass()).Then(Seq([
            App.globalPut(bytes_proposal_result, Bytes("PASSED")),
            If(App.globalGet(bytes_proposal_type)==Bytes("funding"))
            .Then(Seq([
                    withdraw_funds_from_name_registry,
                    withdraw_funds_from_dao_treasury
            ])
            ).ElseIf(App.globalGet(bytes_proposal_type)==Bytes("updatereg"))
            .Then(update_registry_approval_program)
            ])
        ).Else(Seq([
            App.globalPut(bytes_proposal_result, Bytes("REJECTED")),
            
        ])
        ),
        return_deposit,
        ResetProposalParams(),
        Return(Int(1))
    ])

    handle_closeout_or_optin = Seq([
        Assert(Global.group_size() == Int(1)),
        Return(Int(1))
    ])

    program = Cond(
        # Verfies that the application_id is 0, jumps to on_initialize.
        [Txn.application_id() == Int(0), on_initialize],
        # Verifies Update or delete transaction, rejects it.
        [
            Or(
                Txn.on_completion() == OnComplete.UpdateApplication,
                Txn.on_completion() == OnComplete.DeleteApplication
            ),
            Return(Int(0))
        ],
        # Verifies closeout or OptIn transaction, approves it.
        [
            Or(
                Txn.on_completion() == OnComplete.CloseOut,
            ),
            handle_closeout_or_optin
        ],
        [Txn.on_completion() == OnComplete.OptIn, on_register],
        [Txn.application_args[0] == Bytes("opt_in_to_gov_token"), opt_in_to_gov_token],
        [Txn.application_args[0] == Bytes("add_proposal"), add_proposal],
        [Txn.application_args[0] == Bytes("register_vote"), vote],
        [Txn.application_args[0] == Bytes("declare_result"), declare_result],
    )

    return program

with open('contract_approval.teal', 'w') as f:
    compiled = compileTeal(approval_program(12345678), Mode.Application, version=6)
    f.write(compiled)

