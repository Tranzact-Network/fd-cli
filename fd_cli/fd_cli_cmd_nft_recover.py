import click
import requests
import sqlite3
import urllib3

from chia.pools.pool_puzzles import (
    SINGLETON_MOD_HASH,
    create_p2_singleton_puzzle
)

from chia.util.bech32m import (
    decode_puzzle_hash
)

from chia.util.byte_types import (
    hexstr_to_bytes
)

from chia.util.ints import (
    uint64
)

from chia.types.blockchain_format.program import (
    Program,
    SerializedProgram
)

from chia.types.blockchain_format.sized_bytes import (
    bytes32
)

from fd_cli.fd_cli_assert import (
    fd_cli_assert_env_set
)

from fd_cli.fd_cli_cst import (
    FD_CLI_CST_AGGREGATED_SIGNATURE
)

from fd_cli.fd_cli_env import (
    FD_CLI_ENV_BC_DB_PATH,
    FD_CLI_ENV_WT_DB_PATH
)

from fd_cli.fd_cli_print import (
    fd_cli_print_raw,
    fd_cli_print_coin_lite_many,
    fd_cli_print_value
)


def fd_cli_cmd_nft_recover(
        ctx: click.Context,
        delay: int,
        launcher_hash: str,
        pool_contract_address: str,
        node_host: str,
        node_port: int,
        cert_path: str,
        cert_key_path: str,
        cert_ca_path: str
) -> None:
    pre: int = 1
    fd_cli_assert_env_set(FD_CLI_ENV_BC_DB_PATH)
    fd_cli_assert_env_set(FD_CLI_ENV_WT_DB_PATH)

    delay_u64: uint64 = uint64(delay)
    launcher_hash_b32: bytes32 = bytes32(hexstr_to_bytes(launcher_hash))
    contract_hash_b32: bytes32 = decode_puzzle_hash(pool_contract_address)
    contract_hash_hex: str = contract_hash_b32.hex()

    program_puzzle_hex: str = None

    db_wallet_cursor: sqlite3.Cursor = ctx.obj['wt_db'].cursor()
    db_wallet_cursor.execute(
        "SELECT * "
        "FROM  derivation_paths")

    while True:
        derivation_paths: list = db_wallet_cursor.fetchmany(10)

        if len(derivation_paths) == 0:
            break

        for row in derivation_paths:
            puzzle_hash: str = row[2]
            puzzle_hash_b32: bytes32 = bytes32(hexstr_to_bytes(puzzle_hash))

            puzzle = create_p2_singleton_puzzle(
                SINGLETON_MOD_HASH,
                launcher_hash_b32,
                delay_u64,
                puzzle_hash_b32
            )

            if contract_hash_b32 == puzzle.get_tree_hash():
                program_puzzle_hex = bytes(SerializedProgram.from_program(puzzle)).hex()
                break

    if program_puzzle_hex is None:
        fd_cli_print_raw('A valid puzzle program could not be created for the given arguments and the selected wallet.',
                         pre=pre)
        return

    db_bc_cursor: sqlite3.Cursor = ctx.obj['bc_db'].cursor()
    db_bc_cursor.execute(
        f"SELECT * "
        f"FROM coin_record "
        f"WHERE spent == 0 "
        f"AND timestamp <= (strftime('%s', 'now')) "
        f"AND puzzle_hash LIKE '{contract_hash_hex}' "
        f"ORDER BY timestamp DESC")

    coin_records: list = []

    for coin in db_bc_cursor.fetchall():
        coin_amount: int = int.from_bytes(coin[7], byteorder='big', signed=False)

        if coin_amount > 0:
            coin_records.append(coin)

    if len(coin_records) == 0:
        fd_cli_print_raw(f'No coins are eligible for recovery yet. '
                         f'Notice that 604800 seconds must pass since coin creation to recover it.', pre=pre)
        return
    else:
        fd_cli_print_raw('Coins eligible for recovery:', pre=pre)
        fd_cli_print_coin_lite_many(coin_records, pre=pre + 1)
