import pandas as pd
import numpy as np

from utils import log_wrapper

# Obtaining current working directory (necessary for when running with another folder as "Project" in VSCode)
current_directory = '\\'.join(__file__.split("\\")[:-1])


# Load data functions
@log_wrapper
def load_sls_data(file_name: str=f'{current_directory}/../datasets/cigarettes_treated.feather') -> pd.DataFrame:
    '''
        Load the SLS dataset
        Args:
            file_name (str): path to the file to be loaded
        Returns:
            sls (pd.DataFrame): the SLS dataset
    '''
    sls = pd.read_feather(file_name)
    sls['unit_price'] = sls['Dollar_Price'] / sls['Quantity']
    sls = sls.groupby(by=['Store_ID', 'Product_ID', 'Date', 'Day_ID'], as_index=False)[['Quantity', 'unit_price']].agg({'Quantity': 'sum', 'unit_price': 'mean'})
    return sls


@log_wrapper
def load_dimtime_data(file_name: str=f'{current_directory}/../datasets/dim_time.feather') -> pd.DataFrame:
    '''
        Load the DIM_TIME dataset
        Args:
            file_name (str): path to the file to be loaded
        Returns:
            df (pd.DataFrame): the SLS dataset
    '''
    df = pd.read_feather(file_name)
    return df


# Generate purchases from sls dataframe
@log_wrapper
def get_purchases(df: pd.DataFrame, multipliers: tuple[float, float]=(0.3, -0.1)) -> pd.DataFrame:
    '''
        Obtain purchases from a given sales dataset (with AT least columns: Store_ID, Product_ID, Date, Quantity)
        Args:
            sls (pd.DataFrame): the sales dataset
            multipliers (tuple[float, float]): the multipliers to be used to generate the purchases. The first value is the maximum multiplier and the second is the minimum.
        Returns:
            purchases (pd.DataFrame): the purchases dataset
    '''
    sls = df.copy()
    sls['Restock_Weekday'] = (sls.groupby(by=['Store_ID', 'Product_ID'])['Date'].transform('min') - pd.Timedelta(days=1)).dt.weekday
    sls['Last Restock'] = pd.to_datetime((sls['Date'].astype(np.int64) // 10**9) - ((sls['Date'].dt.weekday - sls['Restock_Weekday']) % 7)*24*60*60, unit="s")

    # Checking how much we would have to purchase each week so that the sales are possible and non-negative
    purchases = sls.groupby(by=['Last Restock', 'Store_ID', 'Product_ID'], as_index=False)[['Quantity', 'unit_price']].agg({
        'Quantity': 'sum',
        'unit_price': 'mean'
    }).rename(columns={'Last Restock': 'Date'})

    # Adding a +/- multiplier to the quantity to account for the fact that we will not be able to purchase all of the items
    purchases['multiplier'] = np.random.random(purchases.shape[0])
    # Normalize it to a value between multiplier[1] and multiplier[0] (this will be multiplied by the week's sales qty)
    purchases['multiplier'] = purchases['multiplier'] / np.abs(purchases['multiplier']).max() * multipliers[0] + multipliers[1]

    # Multiply the quantity by the multiplier
    purchases['Quantity'] = (purchases['Quantity'] * (1 + purchases['multiplier'])).round(0).astype(int)
    
    # Calculate the price of the purchase (assuming we have a random margin of a MAX of 10%)
    purchases['Price'] = np.random.random(purchases.shape[0])
    # Normalizing random value to a max of 10%
    purchases['Price'] = purchases['Price'] / np.abs(purchases['Price']).max() * 0.1
    # Updating unit_price according to random variable
    purchases['unit_price'] = purchases['unit_price'] * (1 - purchases['Price'])
    # Calculating price from unit_price and quantity
    purchases['Price'] = purchases['unit_price'] * purchases['Quantity']

    return purchases.drop(columns=['multiplier', 'unit_price'])


@log_wrapper
def get_stocks(purchases: pd.DataFrame, sls: pd.DataFrame) -> pd.DataFrame:
    # ----------------------------------------------------
    # Now that we have sales and stocks, we just have to add stocks minus sales to obtain the inventory.
    # ----------------------------------------------------
    # Use sales as base for stocks table
    stocks = sls[['Product_ID', 'Store_ID', 'Quantity', 'Date']].rename(columns={'Quantity': 'Sales'})
    stocks = stocks.merge(purchases, how='outer').rename(columns={'Quantity': 'Purchases'})
    stocks[['Sales', 'Purchases']] = stocks[['Sales', 'Purchases']].fillna(0)

    # Calculate stocks from purchases and sales
    stocks['Purchases_Cumulative'] = stocks.groupby(by=['Store_ID', 'Product_ID'])['Purchases'].cumsum(skipna=False)
    stocks['Sales_Cumulative'] = stocks.groupby(by=['Store_ID', 'Product_ID'])['Sales'].cumsum(skipna=False)
    stocks['stock_qty'] = (stocks['Purchases_Cumulative'].fillna(0) - stocks['Sales_Cumulative'].fillna(0)).astype(int)

    # Filling stocks table with data for everysingle day
    # Sort stocks by date
    stocks = stocks.sort_values(by=['Store_ID', 'Product_ID', 'Date'], ascending=True)
    # Find the date_range where no stock exists
    stocks['Next_Stock_Date'] = stocks.groupby(by=['Store_ID', 'Product_ID'])['Date'].shift(-1).fillna(stocks['Date'])
    stocks['Date'] = stocks.apply(lambda row: pd.date_range(row['Date'], row['Next_Stock_Date']), axis=1)
    stocks = stocks.explode('Date')     # Explode on Date

    return stocks


def main():
    sls = load_sls_data()
    purchases = get_purchases(sls)
    stocks = get_stocks(purchases, sls)
    dim_time = load_dimtime_data()

    # Add DAY_ID to purchases and Stocks and drop DATE column
    purchases = purchases.merge(dim_time[['Date', 'Day_ID']], how='left').drop(columns=['Date'])
    stocks = stocks.merge(dim_time[['Date', 'Day_ID']], how='left').drop(columns=['Date'])
    print("Writing files...")
    # Writing purchase files
    # purchases.to_csv(f'{current_directory}/../datasets/purchases.csv', index=False)
    purchases.to_feather(f'{current_directory}/../datasets/purchases.feather')
    # Writing Stocks files
    # stocks.to_csv(f'{current_directory}/../datasets/stocks.csv', index=False)
    stocks.to_feather(f'{current_directory}/../datasets/stocks.feather')
    print("Completed")


if __name__ == '__main__':
    main()