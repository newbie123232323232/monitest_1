"""add monitoring core tables

Revision ID: b8c1d2e3f4a5
Revises: a1b2c3d4e5f6
Create Date: 2026-04-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c1d2e3f4a5"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


monitor_type = postgresql.ENUM("http", "tcp", "icmp", name="monitor_type", create_type=False)
monitor_status = postgresql.ENUM(
    "pending", "checking", "up", "down", "slow", "paused", name="monitor_status", create_type=False
)
check_run_status = postgresql.ENUM(
    "up", "down", "slow", "timeout", "dns_error", "tls_error", "http_error", name="check_run_status", create_type=False
)
incident_status = postgresql.ENUM("open", "closed", name="incident_status", create_type=False)
alert_channel = postgresql.ENUM("email", name="alert_channel", create_type=False)
alert_event_type = postgresql.ENUM(
    "incident_opened", "incident_recovered", "still_down", name="alert_event_type", create_type=False
)
alert_send_status = postgresql.ENUM("sent", "failed", name="alert_send_status", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    monitor_type.create(bind, checkfirst=True)
    monitor_status.create(bind, checkfirst=True)
    check_run_status.create(bind, checkfirst=True)
    incident_status.create(bind, checkfirst=True)
    alert_channel.create(bind, checkfirst=True)
    alert_event_type.create(bind, checkfirst=True)
    alert_send_status.create(bind, checkfirst=True)

    op.create_table(
        "monitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("monitor_type", monitor_type, nullable=False, server_default=sa.text("'http'")),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column("slow_threshold_ms", sa.Integer(), nullable=False, server_default=sa.text("1500")),
        sa.Column("detect_content_change", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_paused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "current_status",
            monitor_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_response_time_ms", sa.Integer(), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitors_user_id", "monitors", ["user_id"], unique=False)
    op.create_index("ix_monitors_user_status_paused", "monitors", ["user_id", "current_status", "is_paused"], unique=False)

    op.create_table(
        "check_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", check_run_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("final_url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_check_runs_monitor_id", "check_runs", ["monitor_id"], unique=False)
    op.create_index("ix_check_runs_monitor_started_desc", "check_runs", ["monitor_id", "started_at"], unique=False)

    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", incident_status, nullable=False, server_default=sa.text("'open'")),
        sa.Column("open_reason", sa.Text(), nullable=True),
        sa.Column("close_reason", sa.Text(), nullable=True),
        sa.Column("first_failed_check_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_failed_check_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["first_failed_check_id"], ["check_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_failed_check_id"], ["check_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_monitor_id", "incidents", ["monitor_id"], unique=False)
    op.create_index("ix_incidents_monitor_status", "incidents", ["monitor_id", "status"], unique=False)

    op.create_table(
        "alert_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("monitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", alert_channel, nullable=False, server_default=sa.text("'email'")),
        sa.Column("event_type", alert_event_type, nullable=False),
        sa.Column("sent_to", sa.String(length=320), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("send_status", alert_send_status, nullable=False, server_default=sa.text("'sent'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_events_incident_id", "alert_events", ["incident_id"], unique=False)
    op.create_index("ix_alert_events_monitor_id", "alert_events", ["monitor_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_alert_events_monitor_id", table_name="alert_events")
    op.drop_index("ix_alert_events_incident_id", table_name="alert_events")
    op.drop_table("alert_events")

    op.drop_index("ix_incidents_monitor_status", table_name="incidents")
    op.drop_index("ix_incidents_monitor_id", table_name="incidents")
    op.drop_table("incidents")

    op.drop_index("ix_check_runs_monitor_started_desc", table_name="check_runs")
    op.drop_index("ix_check_runs_monitor_id", table_name="check_runs")
    op.drop_table("check_runs")

    op.drop_index("ix_monitors_user_status_paused", table_name="monitors")
    op.drop_index("ix_monitors_user_id", table_name="monitors")
    op.drop_table("monitors")

    alert_send_status.drop(bind, checkfirst=True)
    alert_event_type.drop(bind, checkfirst=True)
    alert_channel.drop(bind, checkfirst=True)
    incident_status.drop(bind, checkfirst=True)
    check_run_status.drop(bind, checkfirst=True)
    monitor_status.drop(bind, checkfirst=True)
    monitor_type.drop(bind, checkfirst=True)
