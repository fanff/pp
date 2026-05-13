"""db_redesign: merge Convchanges into ConvoMessage, add RBAC + privacy

Revision ID: d8b3a1c2f4e5
Revises: 3f258907f6e5
Create Date: 2026-05-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8b3a1c2f4e5"
down_revision: Union[str, Sequence[str], None] = "3f258907f6e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. Create conv_members table (replaces conv_privacy_members) ---
    op.create_table(
        "conv_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conv_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(), nullable=True, server_default="member"),
        sa.ForeignKeyConstraint(["conv_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["userinfo.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conv_id", "user_id", name="conv_user_uc"),
    )
    op.create_index(op.f("ix_conv_members_id"), "conv_members", ["id"], unique=False)

    # --- 2. Create invite_codes table ---
    op.create_table(
        "invite_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=True),
        sa.Column("creator_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=True, server_default="active"),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.Column("used_at", sa.Float(), nullable=True),
        sa.Column("used_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["creator_id"], ["userinfo.id"]),
        sa.ForeignKeyConstraint(["used_by_id"], ["userinfo.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_invite_codes_id"), "invite_codes", ["id"], unique=False)
    op.create_index(
        op.f("ix_invite_codes_code"), "invite_codes", ["code"], unique=True
    )

    # --- 3. Create friend_requests table ---
    op.create_table(
        "friend_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_user_id", sa.Integer(), nullable=True),
        sa.Column("to_user_id", sa.Integer(), nullable=True),
        sa.Column("invite_code_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=True, server_default="pending"),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["from_user_id"], ["userinfo.id"]),
        sa.ForeignKeyConstraint(["invite_code_id"], ["invite_codes.id"]),
        sa.ForeignKeyConstraint(["to_user_id"], ["userinfo.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_friend_requests_id"), "friend_requests", ["id"], unique=False
    )

    # --- 4. Create friendships table ---
    op.create_table(
        "friendships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_a_id", sa.Integer(), nullable=True),
        sa.Column("user_b_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["user_a_id"], ["userinfo.id"]),
        sa.ForeignKeyConstraint(["user_b_id"], ["userinfo.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_a_id", "user_b_id", name="friendship_uc"),
    )
    op.create_index(op.f("ix_friendships_id"), "friendships", ["id"], unique=False)

    # --- 5. Migrate data from conv_privacy_members to conv_members ---
    conn = op.get_bind()
    existing_members = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM conv_privacy_members"
        )
    ).scalar()
    if existing_members and existing_members > 0:
        conn.execute(
            sa.text(
                "INSERT INTO conv_members (conv_id, user_id, role) "
                "SELECT conv_id, user_id, role FROM conv_privacy_members"
            )
        )

    # --- 6. Add created_at to userinfo and conversations ---
    op.add_column(
        "userinfo",
        sa.Column("created_at", sa.Float(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("created_at", sa.Float(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("updated_at", sa.Float(), nullable=True),
    )

    # --- 7. Add columns to convomessage ---
    op.add_column(
        "convomessage",
        sa.Column("conv_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "convomessage",
        sa.Column("ts", sa.Float(), nullable=True),
    )
    op.add_column(
        "convomessage",
        sa.Column("message_type", sa.String(), nullable=True, server_default="text"),
    )
    op.add_column(
        "convomessage",
        sa.Column("payload", sa.JSON(), nullable=True),
    )

    # --- 8. Migrate data from convchanges to convomessage ---
    rows = conn.execute(
        sa.text(
            "SELECT cc.change_id, cc.conv_id, cc.ts "
            "FROM convchanges cc WHERE cc.change_type = 'message'"
        )
    ).fetchall()
    for row in rows:
        conn.execute(
            sa.text(
                "UPDATE convomessage SET conv_id = :conv_id, ts = :ts WHERE id = :id"
            ),
            {"conv_id": row.conv_id, "ts": row.ts, "id": row.change_id},
        )

    # --- 9. Batch alter convomessage: add FKs, indexes, NOT NULL ---
    with op.batch_alter_table("convomessage") as batch_op:
        batch_op.alter_column("conv_id", nullable=False)
        batch_op.alter_column("ts", nullable=False)
        batch_op.create_index(
            op.f("ix_convomessage_conv_id"), ["conv_id"], unique=False
        )
        batch_op.create_index(op.f("ix_convomessage_ts"), ["ts"], unique=False)
        batch_op.create_index(
            op.f("ix_convomessage_message_type"), ["message_type"], unique=False
        )
        batch_op.create_index(
            op.f("ix_convomessage_sender_id"), ["sender_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_convomessage_conv", "conversations", ["conv_id"], ["id"]
        )

    # --- 10. Drop old tables ---
    op.drop_table("conv_privacy_members")
    op.drop_table("convchanges")


def downgrade() -> None:
    # This is destructive — data loss is expected on rollback.
    # Restore convchanges table
    op.create_table(
        "convchanges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.Float(), nullable=True),
        sa.Column("conv_id", sa.Integer(), nullable=True),
        sa.Column("change_type", sa.String(), nullable=True),
        sa.Column("change_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["change_id"], ["convomessage.id"]),
        sa.ForeignKeyConstraint(["conv_id"], ["conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_convchanges_id"), "convchanges", ["id"], unique=False
    )

    # Recreate conv_privacy_members from conv_members
    op.create_table(
        "conv_privacy_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conv_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["conv_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["userinfo.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conv_id", "user_id", name="conv_user_uc"),
    )
    op.create_index(
        op.f("ix_conv_privacy_members_id"),
        "conv_privacy_members",
        ["id"],
        unique=False,
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO conv_privacy_members (conv_id, user_id, role) "
            "SELECT conv_id, user_id, role FROM conv_members"
        )
    )

    # Drop columns from convomessage (batch mode for SQLite)
    with op.batch_alter_table("convomessage") as batch_op:
        batch_op.drop_constraint("fk_convomessage_conv", type_="foreignkey")
        batch_op.drop_index(op.f("ix_convomessage_conv_id"))
        batch_op.drop_index(op.f("ix_convomessage_ts"))
        batch_op.drop_index(op.f("ix_convomessage_message_type"))
        batch_op.drop_index(op.f("ix_convomessage_sender_id"))
        batch_op.drop_column("conv_id")
        batch_op.drop_column("ts")
        batch_op.drop_column("message_type")
        batch_op.drop_column("payload")

    # Drop added columns
    op.drop_column("conversations", "updated_at")
    op.drop_column("conversations", "created_at")
    op.drop_column("userinfo", "created_at")

    # Drop new tables
    op.drop_table("friendships")
    op.drop_table("friend_requests")
    op.drop_table("invite_codes")
    op.drop_table("conv_members")
