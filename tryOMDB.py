import requests
import json


def get_movie_details(title, year, api_key):
    """
    Fetches movie details from OMDb API by title and year.
    """
    # The 't' parameter is for title, 'y' for year, and 'plot' for plot length
    params = {
        't': title,
        'y': year,
        'plot': 'full',
        'apikey': api_key
    }
    # OMDb API endpoint
    url = "http://www.omdbapi.com/"

    try:
        response = requests.get(url, params=params)
        # Raise an exception for bad status codes
        response.raise_for_status()
        movie_data = response.json()

        # Check if the request was successful
        if movie_data.get("Response") == "True":
            print(f"--- Details for '{movie_data['Title']}' ({movie_data['Year']}) ---")
            print(f"Runtime: {movie_data['Runtime']}")
            print(f"Directors: {movie_data['Director']}")
            print(f"Actors: {movie_data['Actors']}")
            print(f"Plot Synopsis: {movie_data['Plot']}")
            if movie_data['Ratings']:
                print("Ratings:")
                for rating in movie_data['Ratings']:
                    print(f"  - {rating['Source']}: {rating['Value']}")
            return movie_data
        else:
            print(f"Error: {movie_data.get('Error')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"A request error occurred: {e}")
        return None


def main():
    # --- Example Usage ---
    # Replace 'YOUR_API_KEY' with your actual OMDb API key
    API_KEY = 'fd597cf0'
    MOVIE_TITLE = 'Inception'
    MOVIE_YEAR = '2010'

    movie_details = get_movie_details(MOVIE_TITLE, MOVIE_YEAR, API_KEY)

    if True:
        pass


# import cProfile
# if __name__ == '__main__':
#     cProfile.run('main()')
#


if __name__ == '__main__':
    main()
