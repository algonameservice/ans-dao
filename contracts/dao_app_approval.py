from email.parser import BytesParser
import sys
#sys.path.insert(0,'..')

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

    # Verfies deposit of gov_token to an address for a transaction. Args:
    # * tx_index (index of deposit transaction)
    # * receiver (receiver of gov_token)
    def verify_deposit(tx_index: Int, receiver: Addr):
        return Assert(And(
            Global.group_size() >= tx_index,
            Gtxn[tx_index].type_enum() == TxnType.AssetTransfer,
            Gtxn[tx_index].xfer_asset() == Int(ARG_GOV_TOKEN),
            Gtxn[tx_index].asset_receiver() == receiver,
            Gtxn[tx_index].asset_amount() >= Int(0)
        ))

    # scratch vars to save result() & scratch_proposal_active()
    scratchvar_result = ScratchVar(TealType.uint64)
    scratchvar_proposal_active = ScratchVar(TealType.uint64)

    # scratch vars to store proposal config
    scratchvar_voting_start = ScratchVar(TealType.uint64)
    scratchvar_voting_end = ScratchVar(TealType.uint64)
    scratchvar_execute_before = ScratchVar(TealType.uint64)
    scratchvar_proposal_type = ScratchVar(TealType.uint64)

    # propsal is passed if
    # 1. voting is over and
    # 2. proposal.yes >= min_support and
    # 3. proposal.yes > proposal.no
    def is_proposal_passed(idx: Int):
        return And(
            Global.latest_timestamp() > App.localGet(idx, Bytes("voting_end")),
            App.localGet(idx, Bytes("yes")) >= App.globalGet(min_support),
            App.localGet(idx, Bytes("yes")) > App.localGet(idx, Bytes("no"))
        )

    # Computes result of proposal. Saves result in scratch. Args:
    # * idx - index of account where proposal_lsig.address() is passed
    # NOTE: idx == Int(0) means proposalLsig is Txn.sender()
    def compute_result(idx: Int):
        return Seq([
            Cond(
                # 4 if proposal expired (now > proposal.execute_before())
                [Global.latest_timestamp() > App.localGet(idx, Bytes("execute_before")), scratchvar_result.store(Int(4))],
                # 3 if voting is still in progress (now <= voting_end)
                [Global.latest_timestamp() <= App.localGet(idx, Bytes("voting_end")), scratchvar_result.store(Int(3))],
                # 1 if voting is over and proposal.yes >= min_support and proposal.yes > proposal.no
                [
                    is_proposal_passed(idx) == Int(1),
                    scratchvar_result.store(Int(1))
                ],
                [
                    # if proposal is not expired, not in progess, and not passed, then reject (set result == Int(2))
                    And(
                        Global.latest_timestamp() <= App.localGet(idx, Bytes("execute_before")),
                        Global.latest_timestamp() > App.localGet(idx, Bytes("voting_end")),
                        is_proposal_passed(idx) == Int(0)
                    ),
                    scratchvar_result.store(Int(2))
                ]
            ),
        ])

    # Checks if the proposal is active or not. Saves result in scratchvar_proposal_active. Args:
    # * idx - index of account where proposal_lsig.address() is passed
    # NOTE: idx == Int(0) means proposalLsig is Txn.sender()
    def scratch_proposal_active(idx: Int):
        return Seq([
            compute_result(idx),
            If(
                Or(
                    # still in voting (now <= voting_end)
                    Global.latest_timestamp() <= App.localGet(idx, Bytes("voting_end")),
                    # OR succeeded but not executed (now <= execute_before && result() == 1 && executed == 0)
                    And (
                        Global.latest_timestamp() <= App.localGet(idx, Bytes("execute_before")),
                        scratchvar_result.load() == Int(1),
                        App.localGet(idx, Bytes("executed")) == Int(0)
                    )
                ),
                scratchvar_proposal_active.store(Int(1)),
                # NOTE: we store Int(2) as "NO" because Int(0) can also be default value
                scratchvar_proposal_active.store(Int(2)),
            )
        ])

    # global DAO parameters
    # minimum deposit in gov_tokens required to make a proposal
    deposit = App.globalGet(Bytes("deposit"))
    # minimum number of yes power votes to validate the proposal
    min_support = App.globalGet(Bytes("min_support"))
    # minimum voting time (in number of seconds) for a new proposal
    min_duration = App.globalGet(Bytes("min_duration"))
    # maximum voting time (in number of seconds) for a new proposal
    max_duration = App.globalGet(Bytes("max_duration"))
    # a url with more information about the DAO
    url = App.globalGet(Bytes("url"))

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
            #TxnField.xfer_asset: Int(ARG_GOV_TOKEN) # Didn't work
            TxnField.xfer_asset: Txn.assets[0]
        }),
        InnerTxnBuilder.Submit(),
        Return(Int(1))
    ])

    acct_reg_treasury = ScratchVar(TealType.bytes)
    balance_reg_treasury = ScratchVar(TealType.uint64)
    balance_dao_treasury = ScratchVar(TealType.uint64)
    max_funding_amt_algos = ScratchVar(TealType.uint64)
    max_funding_amt_ans = ScratchVar(TealType.uint64)

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

    # Global Vars Proposal:

    # TODO: Init these vars in initialize method
    proposal_id = App.globalGet(Bytes("proposal_id")) # For ex: 123456
    proposal_initiator = Bytes("proposal_initiator_address") # Acct Addr
    proposal_status = Bytes("proposal_status") # Active, Completed
    proposal_type = Bytes("proposal_type") # Social/Funding/UpdateReg
    voting_start = Bytes("voting_start") # Block No.
    voting_end = Bytes("voting_end") # Block No.
    proposal_url = Bytes("proposal_url") # URI
    votecount_yes = Bytes("votecount_yes") # No. of yes
    votecount_no = Bytes("votecount_no") # No. of no
    proposal_funding_amt_algo = Bytes("proposal_funding_amt_algo")
    proposal_funding_amt_ans = Bytes("proposal_funding_amt_asa")
    proposal_funding_amt_recipient = Bytes("proposal_funding_amt_recipient")
    reg_app_id_to_update = Bytes("reg_app_id_to_update")

    # TODO: Remove if not needed, we added separate OptIn
    # Why a separate lsig account address when the smart contract can store the amount?
    # Saves deposit lsig account addresses in app global state
    # Expected arguments: [deposit_lsig]
    add_deposit_accounts = Seq([
        Assert(
            And(
                Global.group_size() == Int(1),
                Global.creator_address() == Txn.sender()
            )
        ),
        App.globalPut(Bytes("deposit_lsig"), Txn.application_args[1]),
        Return(Int(1))
    ])

    def basic_checks(txn: Txn): return And(
        txn.rekey_to() == Global.zero_address(),
        txn.close_remainder_to() == Global.zero_address(),
        txn.asset_close_to() == Global.zero_address()
    )



    # App-args: 
    # Social - [ type Social , duration (no. of days), url ]
    # Funding - [ type Funding , duration (no. of days), url, reg_app_id, amt_algos, amt_ans ]
    # UpdateReg - [ type UpdateReg , duration (no. of days), url, reg_app_id, approval_program ]
    add_proposal = Seq([
        # TODO: Uncomment below once vars are initiatilized
        #Assert(proposal_status == Bytes("completed")),
        Assert(Global.group_size()==Int(2)),

        Assert(
            And(
                Gtxn[0].receiver() == Global.current_application_address(),
                Gtxn[0].amount() == deposit
            )
        ),
        Assert(
            Or(
                Gtxn[1].application_args[1] == Bytes("social"),
                Gtxn[1].application_args[1] == Bytes("funding"),
                Gtxn[1].application_args[1] == Bytes("updatereg"),
            )
        ),

        Assert(Btoi(Gtxn[1].application_args[2])<=max_duration),

        # TODO: do basic checks for txns
        #TODO: do basic checks for url input

        #App.globalPut(Bytes("proposal_id"), Add(proposal_id,Int(1))),
        App.globalPut(Bytes("proposal_id"), Int(1)),
        App.globalPut(Bytes("proposal_initiator"), Gtxn[0].sender()),
        App.globalPut(Bytes("proposal_type"), Gtxn[1].application_args[1]),
        App.globalPut(Bytes("voting_start"), Global.latest_timestamp()),
        App.globalPut(Bytes("voting_end"), Add(App.globalGet(voting_start), Mul(App.globalGet(voting_start),Int(86400)))),
        App.globalPut(Bytes("proposal_url"),Gtxn[1].application_args[3]),
        #Assert(App.globalGet(votecount_yes)==Int(0)),
        #Assert(App.globalGet(votecount_no)==Int(0)),

        store_balance_reg_treasury(Txn.applications[1]),
        max_funding_amt_algos.store(Div(balance_reg_treasury.load(),Int(5))),
        store_balance_dao_treasury(Global.current_application_address()),
        max_funding_amt_ans.store(Div(balance_dao_treasury.load(),Int(5))),
        If(Gtxn[1].application_args[1]==Bytes("funding"))
        .Then(
            Seq( 
                # TODO: Check maybe value
                Assert(
                    And(
                        Btoi(Gtxn[1].application_args[4])>=Int(0),
                        Btoi(Gtxn[1].application_args[4])<=max_funding_amt_algos.load()
                    )
                ),
                App.globalPut(proposal_funding_amt_algo, Btoi(Gtxn[1].application_args[4])),
                Assert(
                    And(
                        Btoi(Gtxn[1].application_args[5])>=Int(0),
                        Btoi(Gtxn[1].application_args[5])<=max_funding_amt_ans.load()
                    )
                ),
                App.globalPut(proposal_funding_amt_ans, Gtxn[1].application_args[5])
            ),
        ).ElseIf(Gtxn[1].application_args[1]==Bytes("UpdateReg"))
        .Then( App.globalPut(reg_app_id_to_update, Btoi(Gtxn[1].application_args[4]))
        ),
        Return(Int(1))
    ])

    # sender.deposit
    sender_deposit = App.localGet(Int(0), Bytes("deposit"))

    # p_<proposal> is a concatenation of p_ with the proposal address to avoid some weird attacks.
    byte_p_proposal = Concat(Bytes("p_"), Txn.accounts[1])
    p_proposal = App.localGetEx(Int(0), Int(0), byte_p_proposal)  # value = proposal.id when a user voted or 0
    yes = Bytes("yes")
    no = Bytes("no")
    abstain = Bytes("abstain")
    '''
    # Register user votes in proposal_lsig by saving Sender.p_<proposal>.
    # * External Accounts: `proposal` : lsig account address with the proposal record (provided as the first external account).
    # * Call arguments: `vote` (bytes): { abstain, yes, no}
    register_vote = Seq([
        p_proposal,
        Assert(
            And(
                Global.group_size() == Int(1),
                # voting_start <= now <= voting_end
                voting_start <= Global.latest_timestamp(),
                Global.latest_timestamp() <= voting_end,
                # Sender.deposit >= 0 (i.e user "deposited" his votes using deposit_vote_token)
                App.localGet(Int(0), Bytes("deposit")) > Int(0)
            )
        ),
        If(
            p_proposal.hasValue() == Int(0),
            # If Sender.p_<proposal> is not set then set p_<proposal> := proposal.id
            App.localPut(Int(0), byte_p_proposal, proposal_id),
            # if Sender.p_<proposal> != proposal.id then overwrite by setting the new proposal.id, fail otherwise
            If(p_proposal.value() != proposal_id,
                App.localPut(Int(0), byte_p_proposal, proposal_id),
                Err()),  # double vote
        ),
        # record vote in proposal_lsig local state (proposal.<counter> += Sender.deposit)
        Cond(
            [Gtxn[0].application_args[1] == yes, App.localPut(Int(1), yes, App.localGet(Int(1), yes) + sender_deposit)],
            [Gtxn[0].application_args[1] == no, App.localPut(Int(1), no, App.localGet(Int(1), no) + sender_deposit)],
            [Gtxn[0].application_args[1] == abstain, App.localPut(Int(1), abstain, App.localGet(Int(1), abstain) + sender_deposit)]
        ),
        # Update Sender.deposit_lock := max(Sender.deposit_lock, proposal.voting_end)
        If(
            App.localGet(Int(0), Bytes("deposit_lock")) <= voting_end,
            App.localPut(Int(0), Bytes("deposit_lock"), voting_end)
        ),
        Return(Int(1))
    ])

    # Clears Sender local state by removing a record of vote cast from a not active proposal. Args:
    # * proposal : lsig account address with the proposal record (provided as the first external account).
    clear_vote_record = Seq([
        p_proposal,
        scratch_proposal_active(Int(1)),
        Assert(Global.group_size() == Int(1)),
        # fail if proposal is active (can’t remove proposal record of an active proposal)
        If(
            # NOTE: here we're only moving forward if "p_propsal is set" (i.e p_proposal.hasValue() == Int(1)),
            # otherwise we don't. Because if we don't do it this way, and value does not exist, then p_proposal.value()
            # will return Int(0) and proposal_id will return Bytes. This will throw a pyTEAL error.
            p_proposal.hasValue() == Int(1),
            If(
                And(
                    p_proposal.value() == proposal_id,
                    # NOTE: 1 means proposal is still in voting.
                    scratchvar_proposal_active.load() == Int(1)
                ) == Int(1),
                Err()
            )
        ),
        # remove record (Sender.p_<proposal>)
        App.localDel(Int(0), byte_p_proposal),
        Return(Int(1))
    ])

    # Executes a proposal (note: anyone can execute a proposal). Args:
    # * proposal : lsig account address with the proposal record (provided as the first external account)
    execute = Seq([
        compute_result(Int(1)), # save result in scratch
        # Assert that the proposal.result() == 1 and proposal.executed == 0
        Assert(
            And(scratchvar_result.load() == Int(1), executed == Int(0))
        ),
        Cond(
            [
                # Int(1) == ALGO transfer
                proposal_type == Int(1),
                Assert(
                    And(
                        Global.group_size() == Int(2),
                        Gtxn[1].type_enum() == TxnType.Payment,
                        Gtxn[1].sender() == proposal_from,
                        Gtxn[1].receiver() == recipient,
                        Gtxn[1].amount() == amount,
                    )
                )
            ],
            [
                # Int(2) == ASA transfer
                proposal_type == Int(2),
                Assert(
                    And(
                        Global.group_size() == Int(2),
                        Gtxn[1].type_enum() == TxnType.AssetTransfer,
                        Gtxn[1].asset_sender() == proposal_from,
                        Gtxn[1].asset_receiver() == recipient,
                        Gtxn[1].asset_amount() == amount,
                        Gtxn[1].xfer_asset() == asa_id,
                    )
                )
            ],
            [
                # Int(3) == Message (no extra transaction)
                proposal_type == Int(3),
                Assert(Global.group_size() == Int(1))
            ]
        ),
        # set proposal.executed := 1
        App.localPut(Int(1), Bytes("executed"), Int(1)),
        Return(Int(1))
    ])

    # load proposal.id
    proposal_id = App.localGetEx(Int(0), Int(0), Bytes("id"))

    # Clears proposal record and returns back the deposit. Arguments:
    # NOTE: proposalLsig is Txn.sender
    clear_proposal = Seq([
        compute_result(Int(0)), # int(0) as proposal_lsig is txn.sender()
        proposal_id,
        # assert that there is a recorded proposal
        Assert(proposal_id.hasValue() == Int(1)),
        Assert(
            And(
                # Assert amount of withdrawal is proposal.deposit & receiver is sender
                Global.group_size() == Int(2),
                Gtxn[1].asset_amount() == App.globalGet(Bytes("deposit")),
                Gtxn[0].sender() == Gtxn[1].asset_receiver(),
                # fees must be paid by tx0(proposer) and not the deposit_lsig
                Gtxn[1].fee() == Int(0),

                # assert that the voting is not active
                Or(
                    # it’s past execution: proposal.executed == 1  || proposal.execute_before < now
                    Or(
                        App.localGet(Int(0), Bytes("executed")) == Int(1),
                        App.localGet(Int(0), Bytes("execute_before")) < Global.latest_timestamp()
                    ) == Int(1),
                    # OR voting failed result() != 1 && proposal.voting_end < now.
                    And(
                        scratchvar_result.load() != Int(1),
                        App.localGet(Int(0), Bytes("voting_end")) < Global.latest_timestamp()
                    ) == Int(1)
                )
            )
        ),
        # clear proposal record (sender == proposer_lsig)
        App.localDel(Int(0), Bytes("name")),
        App.localDel(Int(0), Bytes("url")),
        App.localDel(Int(0), Bytes("url_hash")),
        App.localDel(Int(0), Bytes("hash_algo")),
        App.localDel(Int(0), Bytes("voting_start")),
        App.localDel(Int(0), Bytes("voting_end")),
        App.localDel(Int(0), Bytes("execute_before")),
        App.localDel(Int(0), Bytes("type")),
        App.localDel(Int(0), Bytes("from")),
        App.localDel(Int(0), Bytes("recipient")),
        App.localDel(Int(0), Bytes("asa_id")),
        App.localDel(Int(0), Bytes("amount")),
        App.localDel(Int(0), Bytes("msg")),
        App.localDel(Int(0), Bytes("id")),
        App.localDel(Int(0), Bytes("executed")),
        App.localDel(Int(0), Bytes("yes")),
        App.localDel(Int(0), Bytes("no")),
        App.localDel(Int(0), Bytes("abstain")),
        Return(Int(1))
    ])
    '''

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
                Txn.on_completion() == OnComplete.OptIn
            ),
            handle_closeout_or_optin
        ],
        [Txn.application_args[0] == Bytes("opt_in_to_gov_token"), opt_in_to_gov_token],
        # Verifies add accounts call, jumps to add_deposit_accounts branch.
        #[Txn.application_args[0] == Bytes("add_deposit_accounts"), add_deposit_accounts],
        # Verifies add proposal call, jumps to add_proposal branch.
        [Txn.application_args[0] == Bytes("add_proposal"), add_proposal]
        # Verifies deposit_vote_token call, jumps to deposit_vote_token branch.
        #[Txn.application_args[0] == Bytes("deposit_vote_token"), deposit_vote_token],
        ## Verifies register_vote call, jumps to register_vote branch.
        #[Txn.application_args[0] == Bytes("register_vote"), register_vote],
        ## Verifies execute call, jumps to execute branch.
        #[Txn.application_args[0] == Bytes("execute"), execute],
        ## Verifies withdraw_vote_deposit call, jumps to withdraw_vote_deposit branch.
        #[Txn.application_args[0] == Bytes("withdraw_vote_deposit"), withdraw_vote_deposit],
        ## Verifies clear_vote_record call, jumps to clear_vote_record branch.
        #[Txn.application_args[0] == Bytes("clear_vote_record"), clear_vote_record],
        ## Verifies clear_proposal call, jumps to clear_proposal branch.
        #[Txn.application_args[0] == Bytes("clear_proposal"), clear_proposal]
    )

    return program

with open('dao_app_approval.teal', 'w') as f:
    compiled = compileTeal(approval_program(85778236), Mode.Application, version=6)
    f.write(compiled)