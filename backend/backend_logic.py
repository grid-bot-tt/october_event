import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text
from google.cloud.sql.connector import create_async_connector
from dotenv import load_dotenv
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json

load_dotenv()


async def init_connection_pool():
    async def getconn():
        connector = await create_async_connector()
        conn = await connector.connect_async(
            os.environ["INSTANCE_CONNECTION_NAME"],
            "asyncpg",
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASS"],
            db=os.environ["DB_NAME"],
        )
        return conn

    engine = create_async_engine(
        "postgresql+asyncpg://",
        async_creator=getconn,
    )
    return engine


async def get_db_session():
    engine = await init_connection_pool()
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return async_session()


async def get_kpis():
    async with await get_db_session() as session:
        total_customers = await session.execute(
            text(
                "SELECT COUNT(DISTINCT customer_id) as total_customers FROM customer_360"
            )
        )
        total_customers = (await total_customers.fetchone())[0]

        total_ltv = await session.execute(
            text("SELECT SUM(total_lifetime_value) as total_ltv FROM customer_360")
        )
        total_ltv = (await total_ltv.fetchone())[0]

        avg_order_value = await session.execute(
            text("SELECT AVG(average_order_value) as avg_order_value FROM customer_360")
        )
        avg_order_value = (await avg_order_value.fetchone())[0]

        retention_rate = await session.execute(
            text(
                """
            SELECT CAST(COUNT(CASE WHEN total_purchases > 1 THEN 1 END) AS FLOAT) / COUNT(*) as retention_rate
            FROM customer_360
        """
            )
        )
        retention_rate = (await retention_rate.fetchone())[0]

    return {
        "total_customers": total_customers,
        "total_lifetime_value": round(total_ltv, 2),
        "average_order_value": round(avg_order_value, 2),
        "retention_rate": round(retention_rate * 100, 2),
    }


async def get_customer_segments():
    async with await get_db_session() as session:
        result = await session.execute(
            text(
                "SELECT customer_segment, COUNT(*) as count FROM customer_360 GROUP BY customer_segment"
            )
        )
        df = pd.DataFrame(
            await result.fetchall(), columns=["customer_segment", "count"]
        )

    fig = px.pie(
        df,
        values="count",
        names="customer_segment",
        title="Customer Segment Distribution",
    )
    return json.loads(fig.to_json())


async def get_monthly_revenue():
    async with await get_db_session() as session:
        result = await session.execute(
            text(
                """
            SELECT DATE_TRUNC('month', purchase_date) as month, SUM(total_amount) as revenue
            FROM purchase_transactions
            GROUP BY month
            ORDER BY month
        """
            )
        )
        df = pd.DataFrame(await result.fetchall(), columns=["month", "revenue"])

    fig = px.line(df, x="month", y="revenue", title="Monthly Revenue Trend")
    return json.loads(fig.to_json())


async def get_top_customers():
    async with await get_db_session() as session:
        result = await session.execute(
            text(
                """
            SELECT customer_id, first_name, last_name, total_lifetime_value
            FROM customer_360
            ORDER BY total_lifetime_value DESC
            LIMIT 5
        """
            )
        )
        df = pd.DataFrame(
            await result.fetchall(),
            columns=["customer_id", "first_name", "last_name", "total_lifetime_value"],
        )

    return df.to_dict(orient="records")


async def get_product_category_performance():
    async with await get_db_session() as session:
        result = await session.execute(
            text(
                """
            SELECT pc.category, SUM(pt.total_amount) as total_revenue
            FROM purchase_transactions pt
            JOIN product_catalog pc ON pt.product_id = pc.product_id
            GROUP BY pc.category
            ORDER BY total_revenue DESC
        """
            )
        )
        df = pd.DataFrame(
            await result.fetchall(), columns=["category", "total_revenue"]
        )

    fig = px.bar(
        df, x="category", y="total_revenue", title="Product Category Performance"
    )
    return json.loads(fig.to_json())


async def get_customer_satisfaction():
    async with await get_db_session() as session:
        result = await session.execute(
            text(
                "SELECT AVG(average_satisfaction_score) as avg_satisfaction FROM customer_360"
            )
        )
        avg_satisfaction = (await result.fetchone())[0]

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=avg_satisfaction,
            title={"text": "Customer Satisfaction Score"},
            domain={"x": [0, 1], "y": [0, 1]},
            gauge={
                "axis": {"range": [0, 10]},
                "steps": [
                    {"range": [0, 3], "color": "red"},
                    {"range": [3, 7], "color": "yellow"},
                    {"range": [7, 10], "color": "green"},
                ],
                "threshold": {
                    "line": {"color": "black", "width": 4},
                    "thickness": 0.75,
                    "value": avg_satisfaction,
                },
            },
        )
    )
    return json.loads(fig.to_json())


async def get_churn_risk():
    async with await get_db_session() as session:
        result = await session.execute(
            text(
                "SELECT churn_risk_score, COUNT(*) as count FROM customer_360 GROUP BY churn_risk_score"
            )
        )
        df = pd.DataFrame(
            await result.fetchall(), columns=["churn_risk_score", "count"]
        )

    fig = px.pie(
        df, values="count", names="churn_risk_score", title="Churn Risk Distribution"
    )
    return json.loads(fig.to_json())


async def get_rfm_segmentation():
    async with await get_db_session() as session:
        result = await session.execute(
            text(
                "SELECT recency_score, frequency_score, monetary_score FROM customer_360"
            )
        )
        df = pd.DataFrame(
            await result.fetchall(),
            columns=["recency_score", "frequency_score", "monetary_score"],
        )

    fig = px.scatter_3d(
        df,
        x="recency_score",
        y="frequency_score",
        z="monetary_score",
        title="RFM Segmentation",
        labels={
            "recency_score": "Recency",
            "frequency_score": "Frequency",
            "monetary_score": "Monetary",
        },
    )
    return json.loads(fig.to_json())
