from pyteal import *

def rewards_approval_program():

    # Deploy Dapp when done by DAO smart contract
    # Accept funds from DAO smart contract
    # Take applicable rewards

    dao_dapp_escrow = Txn.accounts[1]
    dao_dapp_id = Btoi(Txn.application_args[0])
    gov_token = Btoi(Txn.application_args[1])

    on_creation = Seq([
        Assert(Txn.sender() == dao_dapp_escrow),
        App.globalPut(Bytes("dao_dapp_id"), dao_dapp_id),
        App.globalPut(Bytes("dao_gov_token"), gov_token),
        Return(Int(1))
    ])

    opt_in_to_gov_token = Seq([
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

    claim_reward = Seq([
        Assert(App.globalGet(Bytes("dao_dapp_id")) == Txn.applications[1]),
        Assert(App.globalGet(Bytes("dao_gov_token")) == Txn.assets[0]),
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.asset_receiver: Txn.sender(),
            TxnField.asset_amount: Int(500),
            TxnField.xfer_asset: Txn.assets[0]
        }),
        InnerTxnBuilder.Next(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.ApplicationCall,
            TxnField.application_id: Txn.applications[1],
            TxnField.application_args: [Bytes("claim_reward")],
            TxnField.applications: [Global.current_application_id()],
            TxnField.accounts: [Txn.sender()]
        }),
        InnerTxnBuilder.Submit(),
        Return(Int(1))
    ])
    
    program = Cond(
        # Verfies that the application_id is 0, jumps to on_initialize.
        [Txn.application_id() == Int(0), on_creation],
        [Txn.application_args[0] == Bytes("opt_in_to_gov_token"), opt_in_to_gov_token],
        # Verifies Update or delete transaction, rejects it.
        [Txn.on_completion() == OnComplete.DeleteApplication, Return(Int(0))],
        [Txn.application_args[0] == Bytes("claim_reward"), claim_reward],
        
    )

    return program

