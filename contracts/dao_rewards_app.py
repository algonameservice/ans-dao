from pyteal import *

def rewards_approval_program():

    # Deploy Dapp when done by DAO smart contract
    # Accept funds from DAO smart contract
    # Take applicable rewards

    dao_dapp_escrow = Txn.accounts[1]
    dao_dapp_id = Btoi(Txn.application_args[0])
    gov_token = Btoi(Txn.application_args[1])
    registry_dapp_id = Btoi(Txn.application_args[2])

    DAO_DAPP_ID = Bytes("dao_dapp_id")
    GOV_ASA_ID = Bytes("dao_gov_token")
    REGISTRY_DAPP_ID = Bytes("registry_dapp_id")

    @Subroutine(TealType.uint64)
    def is_proposal_active():
        return Seq([
            voting_begin := App.globalGetEx(App.globalGet(DAO_DAPP_ID), Bytes("voting_start")),
            voting_end := App.globalGetEx(App.globalGet(DAO_DAPP_ID), Bytes("voting_end")),
            If(
                And(voting_begin.hasValue(), voting_end.hasValue())
            )
            .Then(
                Seq([
                    Assert(
                        And(
                            Global.latest_timestamp() >= voting_begin.value(),
                            Global.latest_timestamp() < voting_end.value()
                        )
                    ),
                    Return(Int(1))
                ])
            ).Else(
                Return(Int(0))
            )
        ])

    valid_contract_creation = And(
        Global.group_size() == Int(3),
        Gtxn[0].type_enum() == TxnType.Payment,
        Gtxn[0].receiver() == Global.current_application_address(),
        Gtxn[0].sender() == dao_dapp_escrow,
        Gtxn[1].application_id() == Global.current_application_id(),
        Gtxn[1].application_args[0] == Bytes("opt_in_to_gov_token"),
        Gtxn[2].type_enum() == TxnType.AssetTransfer,
        Gtxn[2].asset_receiver() == Global.current_application_address()
    )

    on_creation = Seq([
        Assert(Global.group_size() == Int(1)),
        Assert(Txn.sender() == dao_dapp_escrow),
        App.globalPut(DAO_DAPP_ID, dao_dapp_id),
        App.globalPut(GOV_ASA_ID, gov_token),
        App.globalPut(REGISTRY_DAPP_ID, registry_dapp_id),
        Return(Int(1))
    ])

    opt_in_to_gov_token = Seq([
        Assert(valid_contract_creation == Int(1)),
        Assert(App.globalGet(GOV_ASA_ID) == Txn.assets[0]),
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.asset_receiver: Global.current_application_address(),
            TxnField.asset_amount: Int(0),
            TxnField.xfer_asset: Txn.assets[0]
        }),
        InnerTxnBuilder.Submit(),
        Return(Int(1))
    ])

    
    #TODO: Cannot be Txn.sender(), take an account from the accounts array
    #TODO: Have the user opt in to this account to collect rewards
    claim_reward = Seq([
        Assert(App.globalGet(DAO_DAPP_ID) == Txn.applications[1]),
        Assert(App.globalGet(GOV_ASA_ID) == Txn.assets[0]),
        staked_amount := App.localGetEx(Int(0), Int(0), Bytes("staked_amount")),
        rewards_collected := App.localGetEx(Int(0), Int(0), Bytes("rewards_collected")),
        If(rewards_collected.hasValue())
        .Then(Assert(rewards_collected.value() == Bytes("no"))),
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.asset_receiver: Txn.sender(),
            TxnField.asset_amount: Add(staked_amount.value(), Int(500)),
            TxnField.xfer_asset: Txn.assets[0]
        }),
        InnerTxnBuilder.Submit(),
        App.localPut(Int(0), Bytes("rewards_collected"), Bytes("yes")),
        Return(Int(1))
    ])

    stake = Seq([
        Assert(Global.group_size() == Int(3)),
        Assert(
            And(
                Gtxn[0].application_id() == Global.current_application_id(),
                Gtxn[0].application_args[0] == Bytes("stake"),
                Gtxn[1].type_enum() == TxnType.AssetTransfer,
                Gtxn[1].xfer_asset() == App.globalGet(GOV_ASA_ID),
                Gtxn[1].asset_amount() == Btoi(Gtxn[0].application_args[1]),
                Gtxn[1].asset_receiver() == Global.current_application_address(),
                Gtxn[2].application_id() == App.globalGet(DAO_DAPP_ID),
                Gtxn[2].application_args[0] == Bytes("register_vote")
            )
        ),
        App.localPut(Int(0), Bytes("staked_amount"), Gtxn[1].asset_amount()),
        Return(Int(1))
    ])

    #TODO: Check if it is in voting period
    #TODO: Check if user has not voted yet

    address_owns_ans = Seq([
        domain := App.localGetEx(Int(2), App.globalGet(REGISTRY_DAPP_ID), Bytes("owner")),
        If(domain.hasValue())
        .Then(Seq([
            Assert(domain.value() == Txn.sender()),
            Return(Int(1))
        ]))
        .Else(
            Err()
        )
    ])

    delegate = Seq([
        address_owns_ans,
        Assert(is_proposal_active() == Int(1)),
        proposal_last_voted := App.localGetEx(Int(0), App.globalGet(DAO_DAPP_ID), Bytes("proposal_id")),
        current_proposal := App.globalGetEx(App.globalGet(DAO_DAPP_ID), Bytes("proposal_id")),
        If(proposal_last_voted.hasValue())
        .Then(
            Assert(proposal_last_voted.value() != current_proposal.value())
        ),
        Assert(Global.group_size() == Int(2)),
        Assert(
            And(
                Gtxn[0].type_enum() == TxnType.AssetTransfer,
                
                Gtxn[0].asset_receiver() == Global.current_application_address(),
                
                Gtxn[1].application_id() == Global.current_application_id(),
                Gtxn[1].application_args[0] == Bytes("delegate")
            )
        ),
        #TODO: Do we need below line?
        App.localPut(Int(0), Bytes("delegated"), Bytes("yes")),
        App.localPut(Int(0), Bytes("delegated_amount"), Btoi(Txn.application_args[1])),
        App.localPut(Int(0), Bytes("delegated_to"), Txn.accounts[1]),
        delegated_amount := App.localGetEx(Int(1), Int(0), Bytes("delegated_amount")),
        If(delegated_amount.hasValue())
        .Then(App.localPut(Int(1), Bytes("delegated_amount"), Add(delegated_amount.value(), Btoi(Txn.application_args[1]))))
        .Else(App.localPut(Int(1), Bytes("delegated_amount"), Btoi(Txn.application_args[1]))),
        Return(Int(1))
    ])

    undo_delegate = Seq([
        Assert(is_proposal_active() == Int(1)),
        proposal_last_voted := App.localGetEx(Int(1), App.globalGet(DAO_DAPP_ID), Bytes("proposal_id")),
        current_proposal := App.globalGetEx(App.globalGet(DAO_DAPP_ID), Bytes("proposal_id")),
        If(proposal_last_voted.hasValue())
        .Then(
            Assert(proposal_last_voted.value() != current_proposal.value())
        ),
        #Assert(App.localGet(Int(0), Bytes("delegated_to")) == Txn.accounts[1]),
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.asset_receiver: Txn.sender(),
            TxnField.asset_amount: App.localGet(Int(0), Bytes("delegated_amount")),
            TxnField.xfer_asset: Txn.assets[0]
        }),
        InnerTxnBuilder.Submit(),
        App.localPut(Int(0), Bytes("delegated"), Bytes("no")),
        App.localPut(Int(0), Bytes("delegated_amount"), Int(0)),
        App.localPut(Int(0), Bytes("delegated_to"), Bytes("none")),
        App.localPut(Int(1), Bytes("delegated_amount"), Minus(App.localGet(Int(1), Bytes("delegated_amount")), App.localGet(Int(0), Bytes("delegated_amount")))),
        Return(Int(1))
    ])
    
    program = Cond(
        # Verfies that the application_id is 0, jumps to on_initialize.
        [Txn.application_id() == Int(0), on_creation],
        [Txn.on_completion() == OnComplete.OptIn, Return(Int(1))],
        [Txn.on_completion() == OnComplete.DeleteApplication, Return(Int(0))],
        [Txn.application_args[0] == Bytes("opt_in_to_gov_token"), opt_in_to_gov_token],
        [Txn.application_args[0] == Bytes("claim_reward"), claim_reward],
        [Txn.application_args[0] == Bytes("stake"), stake],
        [Txn.application_args[0] == Bytes("delegate"), delegate],
        [Txn.application_args[0] == Bytes("undo_delegate"), undo_delegate],
        
        
    )

    return program

'''
        
        '''