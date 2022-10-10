from pyteal import *

def rewards_approval_program():

    # Deploy Dapp when done by DAO smart contract
    # Accept funds from DAO smart contract
    # Take applicable rewards

    dao_dapp_escrow = Txn.accounts[1]
    dao_dapp_id = Btoi(Txn.application_args[0])
    gov_token = Btoi(Txn.application_args[1])

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
        App.globalPut(Bytes("dao_dapp_id"), dao_dapp_id),
        App.globalPut(Bytes("dao_gov_token"), gov_token),
        Return(Int(1))
    ])

    opt_in_to_gov_token = Seq([
        Assert(valid_contract_creation == Int(1)),
        Assert(App.globalGet(Bytes("dao_gov_token")) == Txn.assets[0]),
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
        Assert(App.globalGet(Bytes("dao_dapp_id")) == Txn.applications[1]),
        Assert(App.globalGet(Bytes("dao_gov_token")) == Txn.assets[0]),
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
                Gtxn[1].xfer_asset() == App.globalGet(Bytes("dao_gov_token")),
                Gtxn[1].asset_amount() == Btoi(Gtxn[0].application_args[1]),
                Gtxn[1].receiver() == Global.current_application_address(),
                Gtxn[2].application_id() == App.globalGet(Bytes("dao_dapp_id")),
                Gtxn[2].application_args[0] == Bytes("register_vote")
            )
        ),
        App.localPut(Int(0), Bytes("staked_amount"), Gtxn[1].asset_amount()),
        Return(Int(1))
    ])

    delegate = Seq([
        Return(Int(1))
    ])

    undo_delegate = Seq([
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

